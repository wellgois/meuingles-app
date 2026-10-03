"""Roda o dbt de verdade (DuckDB) sobre dados sintéticos de resultado conhecido."""
import datetime as dt
import os
import pathlib
import shutil
import subprocess

import pytest

pytest.importorskip("duckdb")
if shutil.which("dbt") is None:
    pytest.skip("dbt não instalado", allow_module_level=True)

import duckdb  # noqa: E402

DBT_DIR = pathlib.Path(__file__).resolve().parents[2] / "dbt"
D = dt.date
TS = dt.datetime(2026, 10, 1, 15, 0, tzinfo=dt.timezone.utc)

DDL = {
    "attempts": "attempt_id bigint, user_key varchar, created_at timestamptz, level int, item_id varchar, engine varchar, "
                "main_score double, accuracy double, completeness double, confidence double, fluency double, "
                "duration_ms int, audio_ms int, word_count int, used_llm boolean, llm_in_tokens int, "
                "llm_out_tokens int, attempt_date date",
    "attempt_words": "attempt_id bigint, seq int, position int, expected varchar, heard varchar, status varchar, "
                     "score double, attempt_created_at timestamptz",
    "attempt_phonemes": "attempt_id bigint, word_seq int, phoneme_seq int, phoneme varchar, score double, "
                        "attempt_created_at timestamptz",
    "visits": "pageview_key varchar, visitor_key varchar, session_key varchar, created_at timestamptz, "
              "updated_at timestamptz, path varchar, ref_host varchar, utm_source varchar, utm_medium varchar, "
              "utm_campaign varchar, utm_content varchar, device varchar, inapp varchar, is_new boolean, "
              "dur_s int, max_scroll int, clicked_cta boolean, visit_date date",
    "users": "user_key varchar, visitor_key varchar, level int, plan varchar, target_level varchar, "
             "email_verified boolean, created_at timestamptz, trial_ends_at timestamptz, paid_until timestamptz, "
             "sub_started_at timestamptz, mp_status varchar, wants_subscription_at timestamptz, "
             "signup_source varchar, signup_campaign varchar, signup_content varchar, is_owner boolean, "
             "is_admin boolean, signup_date date",
    "review_items": "user_key varchar, word varchar, interval_days int, next_due date, misses int, hits int, "
                    "updated_at timestamptz",
}


def attempt(i, user, day, level, engine, score, audio_ms, llm=False, tin=None, tout=None):
    return {"attempt_id": i, "user_key": user, "created_at": TS, "level": level, "item_id": f"w{i}",
            "engine": engine, "main_score": score, "audio_ms": audio_ms, "used_llm": llm,
            "llm_in_tokens": tin, "llm_out_tokens": tout, "attempt_date": day}


def user(key, plan, verified, source, campaign, owner, signup, paid=None):
    return {"user_key": key, "plan": plan, "email_verified": verified, "created_at": TS, "paid_until": paid,
            "signup_source": source, "signup_campaign": campaign, "is_owner": owner, "is_admin": owner,
            "signup_date": signup, "level": 1}


def phoneme(i, ph, score):
    return {"attempt_id": i, "word_seq": 0, "phoneme_seq": 0 if ph == "th" else 1, "phoneme": ph,
            "score": score, "attempt_created_at": TS}


ATTEMPTS = [
    attempt(1, "u1", D(2026, 9, 29), 1, "azure", 80.0, 36000),
    attempt(2, "u1", D(2026, 9, 29), 1, "azure", 90.0, 36000),
    attempt(3, "u1", D(2026, 9, 30), 1, "azure", 70.0, 18000),
    attempt(4, "u1", D(2026, 10, 2), 2, "azure", 85.0, 36000),
    attempt(5, "u1", D(2026, 10, 7), 3, "browser", 75.0, None, True, 1000, 400),
    attempt(6, "u2", D(2026, 9, 30), 1, "azure", 60.0, 72000),
    attempt(7, "o", D(2026, 9, 29), 1, "azure", 100.0, 36000),
    attempt(8, "u1", D(2026, 10, 7), 3, "browser", 65.0, None, True, None, None),
]
USERS = [
    user("u1", "active", True, "linkedin", "c1", False, D(2026, 9, 29), TS),
    user("u2", "trial", True, "linkedin", "c1", False, D(2026, 9, 30)),
    user("u3", "trial", False, None, None, False, D(2026, 10, 6)),
    user("o", "owner", True, None, None, True, D(2026, 9, 1)),
]
PHONEMES = [phoneme(1, "th", 50.0), phoneme(1, "ay", 90.0), phoneme(2, "th", 70.0), phoneme(2, "ay", 100.0),
            phoneme(7, "th", 90.0), phoneme(6, "th", 40.0)]


def insert(con, table, rows):
    for row in rows:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        con.execute(f"insert into silver.{table} ({cols}) values ({marks})", list(row.values()))


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("gold")
    path = tmp / "gold_test.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create schema silver")
    for table, ddl in DDL.items():
        con.execute(f"create table silver.{table} ({ddl})")
    insert(con, "attempts", ATTEMPTS)
    insert(con, "users", USERS)
    insert(con, "attempt_phonemes", PHONEMES)
    con.close()
    env = {**os.environ, "DBT_DUCKDB_PATH": str(path), "DBT_TARGET_PATH": str(tmp / "target"),
           "DBT_LOG_PATH": str(tmp / "logs"), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    result = subprocess.run(
        ["dbt", "build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--target", "local"],
        env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    return path


def rows(path, sql):
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def assert_rows(actual, expected):
    assert len(actual) == len(expected), actual
    for a, e in zip(actual, expected):
        assert len(a) == len(e), (a, e)
        for x, y in zip(a, e):
            if isinstance(y, float):
                assert x == pytest.approx(y), (a, e)
            else:
                assert x == y, (a, e)


def test_progresso_diario(db):
    assert_rows(rows(db, "select user_key, cast(attempt_date as varchar), attempts, avg_main_score, practice_minutes, "
                         "max_level, azure_attempts, llm_attempts, is_owner "
                         "from gold.gold_user_daily_progress order by user_key, attempt_date"), [
        ("o", "2026-09-29", 1, 100.0, 0.6, 1, 1, 0, True),
        ("u1", "2026-09-29", 2, 85.0, 1.2, 1, 2, 0, False),
        ("u1", "2026-09-30", 1, 70.0, 0.3, 1, 1, 0, False),
        ("u1", "2026-10-02", 1, 85.0, 0.6, 2, 1, 0, False),
        ("u1", "2026-10-07", 2, 70.0, 0.0, 3, 0, 2, False),
        ("u2", "2026-09-30", 1, 60.0, 1.2, 1, 1, 0, False)])


def test_fonemas(db):
    assert_rows(rows(db, "select phoneme, attempts, users_count, avg_score, pct_below_80 "
                         "from gold.gold_phoneme_difficulty order by phoneme"), [
        ("ay", 2, 1, 95.0, 0.0),
        ("th", 4, 3, 62.5, 75.0)])


def test_tempo_para_subir_de_nivel(db):
    assert_rows(rows(db, "select user_key, from_level, to_level, cast(from_first_date as varchar), "
                         "cast(to_first_date as varchar), days_to_advance "
                         "from gold.gold_level_progression order by from_level"), [
        ("u1", 1, 2, "2026-09-29", "2026-10-02", 3),
        ("u1", 2, 3, "2026-10-02", "2026-10-07", 5)])


def test_funil_exclui_o_dono(db):
    assert_rows(rows(db, "select signup_source, signup_campaign, signups, verified, practiced, engaged, subscribed "
                         "from gold.gold_funnel_by_source order by signup_source"), [
        ("linkedin", "c1", 2, 2, 2, 1, 1),
        ("sem origem", "", 1, 0, 0, 0, 0)])


def test_retencao_semanal(db):
    assert_rows(rows(db, "select cast(cohort_week as varchar), week_offset, cohort_size, active_users, retention_pct "
                         "from gold.gold_weekly_retention order by cohort_week, week_offset"), [
        ("2026-09-28", 0, 2, 2, 100.0),
        ("2026-09-28", 1, 2, 1, 50.0)])


def test_custo_diario(db):
    assert_rows(rows(db, "select cast(attempt_date as varchar), attempts, azure_hours, azure_cost_usd, llm_calls, "
                         "llm_calls_measured, llm_in_tokens, llm_out_tokens, llm_cost_usd, total_cost_usd "
                         "from gold.gold_daily_cost order by attempt_date"), [
        ("2026-09-29", 3, 0.03, 0.0396, 0, 0, 0, 0, 0.0, 0.0396),
        ("2026-09-30", 2, 0.025, 0.033, 0, 0, 0, 0, 0.0, 0.033),
        ("2026-10-02", 1, 0.01, 0.0132, 0, 0, 0, 0, 0.0, 0.0132),
        ("2026-10-07", 2, 0.0, 0.0, 2, 1, 1800, 900, 0.0063, 0.0063)])
