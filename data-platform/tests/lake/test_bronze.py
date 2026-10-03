import datetime as dt
import os
import shutil

import pytest

pytest.importorskip("pyspark")
pytest.importorskip("delta")

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from extractor import tables as T  # noqa: E402
from lake import jobs  # noqa: E402

TS = dt.datetime(2026, 10, 1, 15, 0, tzinfo=dt.timezone.utc)
UA, UB, VA, VB = "a" * 32, "b" * 32, "c" * 32, "d" * 32
D1, D2, D3 = dt.date(2026, 10, 1), dt.date(2026, 10, 2), dt.date(2026, 10, 3)


def write(root, table, partition, rows):
    t = pa.Table.from_pylist(rows, schema=pa.schema(T.SPECS[table].schema))
    folder = os.path.join(root, "landing", table, partition)
    os.makedirs(folder, exist_ok=True)
    pq.write_table(t, os.path.join(folder, "part-0.parquet"))


def write_day(root, d, attempts):
    """Um dia de landing: as tentativas e, para cada uma, 1 palavra e 1 fonema."""
    part = f"dt={d.isoformat()}"
    write(root, "attempts", part, [
        {"attempt_id": i, "user_key": u, "created_at": TS, "level": 1, "item_id": f"w{i}", "engine": "azure",
         "main_score": 80.0, "audio_ms": 4000, "used_llm": False} for i, u in attempts])
    write(root, "attempt_words", part, [
        {"attempt_id": i, "seq": 0, "expected": "job", "heard": "job", "status": "ok", "score": 90.0,
         "attempt_created_at": TS} for i, _ in attempts])
    write(root, "attempt_phonemes", part, [
        {"attempt_id": i, "word_seq": 0, "phoneme_seq": 0, "phoneme": "jh", "score": 70.0,
         "attempt_created_at": TS} for i, _ in attempts])


def visit(key, vid):
    return {"pageview_key": key, "visitor_key": vid, "session_key": "s" * 32, "created_at": TS, "updated_at": TS,
            "path": "/", "dur_s": 5, "device": "desktop", "is_new": True, "clicked_cta": False}


@pytest.fixture()
def landing(tmp_path):
    root = str(tmp_path)
    write_day(root, D1, [(1, UA), (2, UA), (3, UB)])
    write_day(root, D2, [(4, UA)])
    write(root, "visits", "dt=2026-10-01", [visit("e" * 32, VA), visit("f" * 32, VB)])
    write(root, "visits", "dt=2026-10-02", [])
    snap = "snapshot=2026-10-02"
    write(root, "users", snap, [
        {"user_key": UA, "visitor_key": VA, "level": 1, "plan": "trial", "created_at": TS},
        {"user_key": UB, "visitor_key": VB, "level": 1, "plan": "trial", "created_at": TS}])
    write(root, "review_items", snap, [
        {"user_key": UA, "word": "job", "interval_days": 1, "misses": 1, "hits": 0},
        {"user_key": UB, "word": "job", "interval_days": 1, "misses": 1, "hits": 0}])
    write(root, "deleted_users", snap, [])
    return root


def bronze(spark, root, table):
    return spark.read.format("delta").load(f"{root}/bronze/{table}")


def test_bronze_copia_e_e_idempotente(spark, landing):
    first = jobs.run_bronze(spark, landing, D1, D2)
    second = jobs.run_bronze(spark, landing, D1, D2)
    assert first == second
    assert first == {"attempts": 4, "attempt_words": 4, "attempt_phonemes": 4, "visits": 2,
                     "users": 2, "review_items": 2, "deleted_users": 0}


def test_so_toca_na_janela(spark, landing):
    jobs.run_bronze(spark, landing, D1, D2)
    # a landing perde o dia 1 (retenção); ingerir só o dia 2 não pode apagar o dia 1 do bronze
    shutil.rmtree(os.path.join(landing, "landing", "attempts", "dt=2026-10-01"))
    jobs.run_bronze(spark, landing, D2, D2)
    assert bronze(spark, landing, "attempts").count() == 4


def test_exclusao_apaga_tudo_do_usuario_e_nao_ressuscita(spark, landing):
    jobs.run_bronze(spark, landing, D1, D2)
    write(landing, "deleted_users", "snapshot=2026-10-03", [{"user_key": UA, "visitor_key": VA, "deleted_at": TS}])

    def check():
        c = jobs.count_rows(spark, landing, "bronze")
        assert (c["attempts"], c["attempt_words"], c["attempt_phonemes"]) == (1, 1, 1)
        assert (c["visits"], c["users"], c["review_items"], c["deleted_users"]) == (1, 1, 1, 1)
        for table in ("attempts", "attempt_words", "attempt_phonemes"):
            assert [r.attempt_id for r in bronze(spark, landing, table).collect()] == [3]
        assert bronze(spark, landing, "visits").where(F.col("visitor_key") == VA).count() == 0
        assert bronze(spark, landing, "users").where(F.col("user_key") == UA).count() == 0

    jobs.run_bronze(spark, landing, D1, D3)
    check()
    jobs.run_bronze(spark, landing, D1, D3)  # a landing antiga ainda tem a conta excluída
    check()
