"""Checagens de qualidade da camada silver: falham o job em vez de deixar dado ruim passar."""
from delta.tables import DeltaTable
from pyspark.sql import functions as F

from . import jobs


class QualityError(RuntimeError):
    pass


def _out_of_range(col):
    c = F.col(col)
    return c.isNotNull() & ((c < 0) | (c > 100))


def check_batch(frames):
    """Regras sobre o lote que vai entrar no silver (antes do MERGE)."""
    rules = [
        ("attempts", F.col("main_score").isNull() | (F.col("main_score") < 0) | (F.col("main_score") > 100),
         "attempts.main_score fora de 0-100 ou nulo"),
        ("attempts", _out_of_range("accuracy"), "attempts.accuracy fora de 0-100"),
        ("attempts", _out_of_range("completeness"), "attempts.completeness fora de 0-100"),
        ("attempts", _out_of_range("fluency"), "attempts.fluency fora de 0-100"),
        ("attempts", ~F.col("level").between(1, 5) | F.col("level").isNull(), "attempts.level fora de 1-5"),
        ("attempts", ~F.col("engine").isin("browser", "azure") | F.col("engine").isNull(),
         "attempts.engine desconhecido"),
        ("attempts", F.col("audio_ms") < 0, "attempts.audio_ms negativo"),
        ("attempt_words", _out_of_range("score"), "attempt_words.score fora de 0-100"),
        ("attempt_phonemes", _out_of_range("score"), "attempt_phonemes.score fora de 0-100"),
        ("visits", F.col("dur_s") < 0, "visits.dur_s negativo"),
    ]
    fails = []
    for table, cond, msg in rules:
        n = frames[table].where(cond).count()
        if n:
            fails.append(f"{msg}: {n} linhas")
    return fails


def check_orphans(spark, root):
    """Palavras e fonemas precisam ter a tentativa correspondente no silver."""
    attempts_path = jobs.layer_path(root, "silver", "attempts")
    if not DeltaTable.isDeltaTable(spark, attempts_path):
        return []
    parents = spark.read.format("delta").load(attempts_path).select("attempt_id")
    fails = []
    for table in ("attempt_words", "attempt_phonemes"):
        path = jobs.layer_path(root, "silver", table)
        if DeltaTable.isDeltaTable(spark, path):
            n = spark.read.format("delta").load(path).join(parents, "attempt_id", "left_anti").count()
            if n:
                fails.append(f"silver.{table}: {n} linhas sem tentativa correspondente")
    return fails
