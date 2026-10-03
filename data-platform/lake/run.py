"""Ponto de entrada do job (Databricks ou local): python -m lake.run --root <raiz do lake>"""
import argparse
import datetime as dt
from zoneinfo import ZoneInfo

from pyspark.sql import SparkSession

from . import jobs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, help="raiz do lake, com as pastas landing/ e bronze/")
    ap.add_argument("--from", dest="start", help="primeira data (AAAA-MM-DD); padrão: 3 dias antes do fim")
    ap.add_argument("--to", dest="end", help="última data (AAAA-MM-DD); padrão: hoje (Brasília)")
    a = ap.parse_args(argv)
    today = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    end = dt.date.fromisoformat(a.end) if a.end else today
    start = dt.date.fromisoformat(a.start) if a.start else end - dt.timedelta(days=3)
    spark = SparkSession.builder.getOrCreate()
    print(jobs.run_bronze(spark, a.root, start, end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
