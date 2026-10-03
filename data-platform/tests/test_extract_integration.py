"""Teste com banco real. Só roda com EXTRACT_TEST_DB definido (nunca aponte para a produção)."""
import datetime as dt
import os
import uuid
from pathlib import Path

import psycopg
import pyarrow.parquet as pq
import pytest
from psycopg.types.json import Jsonb

from extractor import pseudo, run

URL = os.environ.get("EXTRACT_TEST_DB")
SCHEMA = Path(__file__).resolve().parents[2] / "api" / "app" / "schema.sql"
KEY = b"t" * 32
DAY = dt.date(2020, 1, 15)
pytestmark = pytest.mark.skipif(not URL, reason="EXTRACT_TEST_DB não definido")


@pytest.fixture()
def conn():
    c = psycopg.connect(URL, autocommit=True)
    c.execute(SCHEMA.read_text(encoding="utf-8"))
    yield c
    c.close()


def read(base, table, partition):
    return pq.read_table(base / table / partition / "part-0.parquet")


def test_extrai_pseudonimiza_e_nao_vaza(conn, tmp_path):
    uid, vid = uuid.uuid4(), str(uuid.uuid4())
    email = f"{uid}@example.test"
    ts = dt.datetime(2020, 1, 15, 12, 0, tzinfo=run.TZ)
    conn.execute("INSERT INTO users (id, name, email, plan, signup_source, signup_vid) "
                 "VALUES (%s, 'Pessoa Secreta', %s, 'trial', 'linkedin', %s)", (uid, email, vid))
    raw = {"request": {}, "result": {
        "words": [{"expected": "idempotent", "phonemes": [{"p": "ay", "score": 80.5}, {"p": "d", "score": 60}]},
                  {"expected": "job", "phonemes": []}],
        "llm": {"usage": {"in": 800, "out": 500}}}}
    aid = conn.execute(
        """INSERT INTO attempts (user_id, created_at, level, item_id, target_text, transcript, engine,
                                 main_score, audio_ms, used_llm, raw)
           VALUES (%s, %s, 1, 'w1', 'idempotent', 'texto falado sigiloso', 'azure', 85.5, 4000, true, %s)
           RETURNING id""", (uid, ts, Jsonb(raw))).fetchone()[0]
    conn.execute("INSERT INTO attempt_words (attempt_id, seq, position, expected, heard, status, score) VALUES "
                 "(%s, 0, 0, 'idempotent', 'idempotent', 'ok', 90), (%s, 1, 1, 'job', 'jab', 'wrong', 40)", (aid, aid))
    conn.execute("INSERT INTO visits (pv, vid, sid, created_at, path, utm_source) VALUES (%s, %s, %s, %s, '/', 'linkedin')",
                 (uuid.uuid4(), vid, str(uuid.uuid4()), ts))
    try:
        c2 = run.connect(URL)
        try:
            counts = run.extract_day(c2, DAY, str(tmp_path), KEY)
            run.extract_snapshots(c2, DAY, str(tmp_path), KEY)
        finally:
            c2.close()

        assert counts == {"attempts": 1, "attempt_words": 2, "attempt_phonemes": 2, "visits": 1}
        uk = pseudo.pseudo(KEY, uid)
        at = read(tmp_path, "attempts", "dt=2020-01-15").to_pylist()
        assert at[0]["user_key"] == uk and at[0]["llm_in_tokens"] == 800 and at[0]["llm_out_tokens"] == 500
        ph = read(tmp_path, "attempt_phonemes", "dt=2020-01-15").to_pylist()
        assert [(r["word_seq"], r["phoneme_seq"], r["phoneme"]) for r in ph] == [(0, 0, "ay"), (0, 1, "d")]
        me = [u for u in read(tmp_path, "users", "snapshot=2020-01-15").to_pylist() if u["user_key"] == uk]
        assert me and me[0]["visitor_key"] == pseudo.pseudo(KEY, vid) and me[0]["signup_source"] == "linkedin"

        values = []
        for p in tmp_path.rglob("*.parquet"):
            t = pq.read_table(p)
            assert not {"transcript", "email", "name", "pass_hash", "target_text", "raw"} & set(t.column_names)
            for col in t.column_names:
                values += [str(v) for v in t.column(col).to_pylist() if v is not None]
        joined = "\n".join(values)
        for secret in (email, "Pessoa Secreta", "texto falado sigiloso", str(uid), vid):
            assert secret not in joined
    finally:
        conn.execute("DELETE FROM users WHERE id = %s", (uid,))


def test_exclusao_vai_para_a_lista_de_supressao(conn, tmp_path):
    uid, vid = uuid.uuid4(), str(uuid.uuid4())
    conn.execute("INSERT INTO users (id, name, email, signup_vid) VALUES (%s, 'X', %s, %s)",
                 (uid, f"{uid}@example.test", vid))
    conn.execute("INSERT INTO visits (pv, vid, sid, path) VALUES (%s, %s, %s, '/')",
                 (uuid.uuid4(), vid, str(uuid.uuid4())))
    conn.execute("DELETE FROM users WHERE id = %s", (uid,))
    assert conn.execute("SELECT count(*) FROM visits WHERE vid = %s", (vid,)).fetchone()[0] == 0
    c2 = run.connect(URL)
    try:
        run.extract_snapshots(c2, DAY, str(tmp_path), KEY)
    finally:
        c2.close()
    rows = read(tmp_path, "deleted_users", "snapshot=2020-01-15").to_pylist()
    assert pseudo.pseudo(KEY, uid) in [r["user_key"] for r in rows]
