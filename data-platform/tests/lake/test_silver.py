import pytest

pytest.importorskip("pyspark")
pytest.importorskip("delta")

from delta.tables import DeltaTable  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from lake import jobs, quality, silver  # noqa: E402
from test_bronze import D1, D2, D3, TS, UA, UB, VA, landing, write  # noqa: E402,F401


def attempt_row(i, user, score=80.0):
    return {"attempt_id": i, "user_key": user, "created_at": TS, "level": 1, "item_id": f"w{i}",
            "engine": "azure", "main_score": score, "audio_ms": 4000, "used_llm": False}


def table(spark, root, name):
    return spark.read.format("delta").load(f"{root}/silver/{name}")


def run_all(spark, root, start=D1, end=D2):
    jobs.run_bronze(spark, root, start, end)
    return silver.run_silver(spark, root)


def test_silver_tipado_e_idempotente(spark, landing):
    first = run_all(spark, landing)
    second = run_all(spark, landing)
    assert first == second
    assert first == {"attempts": 4, "attempt_words": 4, "attempt_phonemes": 4, "visits": 2,
                     "users": 2, "review_items": 2, "deleted_users": 0}
    attempts = table(spark, landing, "attempts")
    assert str(attempts.where(F.col("attempt_id") == 1).collect()[0].attempt_date) == "2026-10-01"
    assert "dt" not in attempts.columns


def test_merge_atualiza_sem_duplicar(spark, landing):
    run_all(spark, landing)
    write(landing, "attempts", "dt=2026-10-01",
          [attempt_row(1, UA, 55.0), attempt_row(2, UA), attempt_row(3, UB)])
    counts = run_all(spark, landing)
    assert counts["attempts"] == 4
    assert table(spark, landing, "attempts").where(F.col("attempt_id") == 1).collect()[0].main_score == 55.0


def test_exclusao_chega_ao_silver(spark, landing):
    run_all(spark, landing)
    write(landing, "deleted_users", "snapshot=2026-10-03", [{"user_key": UA, "visitor_key": VA, "deleted_at": TS}])
    counts = run_all(spark, landing, D1, D3)
    assert (counts["attempts"], counts["attempt_words"], counts["attempt_phonemes"]) == (1, 1, 1)
    assert (counts["visits"], counts["users"], counts["review_items"]) == (1, 1, 1)
    assert [r.attempt_id for r in table(spark, landing, "attempts").collect()] == [3]
    assert table(spark, landing, "users").where(F.col("user_key") == UA).count() == 0


def test_nota_invalida_barra_o_silver(spark, landing):
    write(landing, "attempts", "dt=2026-10-01",
          [attempt_row(1, UA, 150.0), attempt_row(2, UA), attempt_row(3, UB)])
    jobs.run_bronze(spark, landing, D1, D2)
    with pytest.raises(quality.QualityError):
        silver.run_silver(spark, landing)
    assert not DeltaTable.isDeltaTable(spark, f"{landing}/silver/attempts")


def test_orfao_e_detectado(spark, landing):
    rows = [{"attempt_id": i, "seq": 0, "expected": "job", "heard": "job", "status": "ok", "score": 90.0,
             "attempt_created_at": TS} for i in (1, 2, 3, 99)]
    write(landing, "attempt_words", "dt=2026-10-01", rows)
    jobs.run_bronze(spark, landing, D1, D2)
    with pytest.raises(quality.QualityError, match="sem tentativa"):
        silver.run_silver(spark, landing)
