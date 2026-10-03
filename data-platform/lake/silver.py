"""Camada silver: dados tipados e deduplicados, gravados com MERGE idempotente."""
from delta.tables import DeltaTable
from pyspark.sql import Window
from pyspark.sql import functions as F

from . import jobs, quality

TZ = "America/Sao_Paulo"
KEYS = {
    "attempts": ["attempt_id"],
    "attempt_words": ["attempt_id", "seq"],
    "attempt_phonemes": ["attempt_id", "word_seq", "phoneme_seq"],
    "visits": ["pageview_key"],
    "users": ["user_key"],
    "review_items": ["user_key", "word"],
}
ORDER = ["attempts", "attempt_words", "attempt_phonemes", "visits", "users", "review_items"]


def _bronze(spark, root, table):
    return spark.read.format("delta").load(jobs.layer_path(root, "bronze", table))


def _latest(df, keys, order_col="_ingested_at"):
    """Uma linha por chave: a versão mais recente."""
    w = Window.partitionBy(*keys).orderBy(F.col(order_col).desc(), F.col("_ingested_at").desc())
    return df.withColumn("_rn", F.row_number().over(w)).where(F.col("_rn") == 1).drop("_rn")


def _local_date(col):
    return F.to_date(F.from_utc_timestamp(F.col(col), TZ))


def build_frames(spark, root):
    def get(table, part):
        df = _latest(_bronze(spark, root, table), KEYS[table], part)
        return df.drop(part, "_ingested_at", "_source_file")

    # tabelas diárias: partição dt; dimensões: partição snapshot (vale a mais recente)
    attempts = get("attempts", "dt").withColumn("attempt_date", _local_date("created_at"))
    visits = get("visits", "dt").withColumn("visit_date", _local_date("created_at"))
    return {
        "attempts": attempts,
        "attempt_words": get("attempt_words", "dt"),
        "attempt_phonemes": get("attempt_phonemes", "dt"),
        "visits": visits,
        "users": get("users", "snapshot"),
        "review_items": get("review_items", "snapshot"),
    }


def merge_upsert(spark, path, df, keys):
    if not DeltaTable.isDeltaTable(spark, path):
        df.write.format("delta").mode("overwrite").save(path)
        return
    cond = " AND ".join(f"t.{k} = s.{k}" for k in keys)
    (DeltaTable.forPath(spark, path).alias("t").merge(df.alias("s"), cond)
        .whenMatchedUpdateAll().whenNotMatchedInsertAll().execute())


def run_silver(spark, root):
    frames = build_frames(spark, root)
    fails = quality.check_batch(frames)
    if fails:
        raise quality.QualityError("; ".join(fails))
    for table in ORDER:
        merge_upsert(spark, jobs.layer_path(root, "silver", table), frames[table], KEYS[table])
    jobs.suppress(spark, root, "silver")
    fails = quality.check_orphans(spark, root)
    if fails:
        raise quality.QualityError("; ".join(fails))
    return jobs.count_rows(spark, root, "silver")
