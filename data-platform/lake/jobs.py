"""Camada bronze: cópia da landing em Delta, idempotente por janela de datas.
Supressão: apaga das camadas tudo o que pertence às contas excluídas (tabela deleted_users)."""
from delta.tables import DeltaTable
from pyspark.sql import functions as F

from . import spec


def layer_path(root: str, layer: str, table: str) -> str:
    return f"{root.rstrip('/')}/{layer}/{table}"


def _date_lit(d) -> str:
    return f"DATE'{d.isoformat()}'"


def ingest_bronze(spark, root, table, start, end):
    """Substitui no bronze as partições [start, end] pelo conteúdo atual da landing. Nunca toca fora da janela."""
    part = spec.partition_col(table)
    df = spark.read.parquet(layer_path(root, "landing", table))
    df = df.filter((F.col(part) >= F.lit(start)) & (F.col(part) <= F.lit(end)))
    df = df.withColumn("_ingested_at", F.current_timestamp()).withColumn("_source_file", F.input_file_name())
    predicate = f"{part} >= {_date_lit(start)} AND {part} <= {_date_lit(end)}"
    (df.write.format("delta").mode("overwrite").partitionBy(part)
       .option("replaceWhere", predicate).save(layer_path(root, "bronze", table)))


def _deleted(spark, root):
    path = layer_path(root, "bronze", "deleted_users")
    if not DeltaTable.isDeltaTable(spark, path):
        return None
    d = spark.read.format("delta").load(path).select("user_key", "visitor_key").distinct().cache()
    if d.count() == 0:
        d.unpersist()
        return None
    return d


def _merge_delete(spark, path, source, cond):
    if not DeltaTable.isDeltaTable(spark, path):
        return
    (DeltaTable.forPath(spark, path).alias("t").merge(source.alias("s"), cond)
        .whenMatchedDelete().execute())


def suppress(spark, root, layer):
    """Apaga de uma camada tudo o que pertence às contas de deleted_users (filhos antes dos pais)."""
    deleted = _deleted(spark, root)
    if deleted is None:
        return
    users = deleted.select("user_key").distinct()
    visitors = deleted.where(F.col("visitor_key").isNotNull()).select("visitor_key").distinct()

    def p(table):
        return layer_path(root, layer, table)

    if DeltaTable.isDeltaTable(spark, p("attempts")):
        doomed = (spark.read.format("delta").load(p("attempts")).join(users, "user_key")
                  .select("attempt_id").distinct().cache())
        doomed.count()
        _merge_delete(spark, p("attempt_phonemes"), doomed, "t.attempt_id = s.attempt_id")
        _merge_delete(spark, p("attempt_words"), doomed, "t.attempt_id = s.attempt_id")
        doomed.unpersist()
    _merge_delete(spark, p("attempts"), users, "t.user_key = s.user_key")
    _merge_delete(spark, p("visits"), visitors, "t.visitor_key = s.visitor_key")
    _merge_delete(spark, p("users"), users, "t.user_key = s.user_key")
    _merge_delete(spark, p("review_items"), users, "t.user_key = s.user_key")
    deleted.unpersist()


def count_rows(spark, root, layer):
    out = {}
    for t in spec.ALL:
        path = layer_path(root, layer, t)
        out[t] = spark.read.format("delta").load(path).count() if DeltaTable.isDeltaTable(spark, path) else 0
    return out


def run_bronze(spark, root, start, end):
    for t in spec.ALL:
        ingest_bronze(spark, root, t, start, end)
    suppress(spark, root, "bronze")
    return count_rows(spark, root, "bronze")
