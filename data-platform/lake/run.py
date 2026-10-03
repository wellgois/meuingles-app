"""Ponto de entrada do job (Databricks ou local): python -m lake.run --root <raiz do lake>"""
import argparse
import datetime as dt
import os
from zoneinfo import ZoneInfo

from pyspark.sql import SparkSession

from . import jobs, silver


def get_spark():
    """No Databricks a sessão já vem com Delta; localmente, configura o Delta (precisa do pacote delta-spark)."""
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        return SparkSession.builder.getOrCreate()
    from delta import configure_spark_with_delta_pip
    builder = (SparkSession.builder.master("local[2]").appName("meuingles-lake")
               .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
               .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
               .config("spark.ui.enabled", "false")
               .config("spark.sql.session.timeZone", "UTC"))
    return configure_spark_with_delta_pip(builder).getOrCreate()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, help="raiz do lake, com as pastas landing/, bronze/ e silver/")
    ap.add_argument("--from", dest="start", help="primeira data (AAAA-MM-DD); padrão: 3 dias antes do fim")
    ap.add_argument("--to", dest="end", help="última data (AAAA-MM-DD); padrão: hoje (Brasília)")
    a = ap.parse_args(argv)
    today = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    end = dt.date.fromisoformat(a.end) if a.end else today
    start = dt.date.fromisoformat(a.start) if a.start else end - dt.timedelta(days=3)
    spark = get_spark()
    print("bronze", jobs.run_bronze(spark, a.root, start, end))
    print("silver", silver.run_silver(spark, a.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
