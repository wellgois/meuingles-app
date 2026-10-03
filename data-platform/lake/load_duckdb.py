"""Carrega as tabelas Delta do silver em um banco DuckDB local (schema silver), para o dbt rodar sem custo."""
import argparse
import os

import duckdb
from deltalake import DeltaTable

TABLES = ["attempts", "attempt_words", "attempt_phonemes", "visits", "users", "review_items"]


def load(silver_root: str, db_path: str) -> dict:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    con = duckdb.connect(db_path)
    try:
        con.execute("create schema if not exists silver")
        counts = {}
        for table in TABLES:
            path = os.path.join(silver_root, table)
            if not os.path.isdir(path):
                raise FileNotFoundError(f"Tabela silver ausente: {path}")
            con.register("_src", DeltaTable(path).to_pyarrow_table())
            con.execute(f"create or replace table silver.{table} as select * from _src")
            con.unregister("_src")
            counts[table] = con.execute(f"select count(*) from silver.{table}").fetchone()[0]
        return counts
    finally:
        con.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--silver", required=True, help="pasta do silver (uma subpasta Delta por tabela)")
    ap.add_argument("--db", required=True, help="arquivo DuckDB de saída")
    a = ap.parse_args(argv)
    print(load(a.silver, a.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
