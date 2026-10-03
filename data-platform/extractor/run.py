"""Extrator diário: Postgres -> Parquet pseudonimizado, com checagens de qualidade antes de gravar."""
import argparse
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

import psycopg
import pyarrow.parquet as pq
from psycopg.rows import dict_row

from . import pseudo, quality
from . import tables as T

TZ = ZoneInfo("America/Sao_Paulo")


class QualityError(RuntimeError):
    def __init__(self, label, failures):
        super().__init__(f"{label}: " + "; ".join(failures))
        self.label, self.failures = label, failures


def connect(url):
    """Conexão somente leitura, com uma fotografia consistente do banco por transação."""
    conn = psycopg.connect(url, row_factory=dict_row)
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    conn.read_only = True
    return conn


def day_bounds(day):
    start = dt.datetime.combine(day, dt.time.min, tzinfo=TZ)
    return start, start + dt.timedelta(days=1)


def build(conn, names, key, params=None):
    return {n: T.to_table(conn.execute(T.SPECS[n].sql, params).fetchall(), T.SPECS[n], key) for n in names}


def write_parquet(table, path):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, "." + os.path.basename(path) + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)          # troca atômica: rodar de novo sobrescreve a mesma partição


def publish(tables, out, partition):
    counts = {}
    for name, t in tables.items():
        write_parquet(t, os.path.join(out, name, partition, "part-0.parquet"))
        counts[name] = t.num_rows
    return counts


def extract_day(conn, day, out, key):
    start, end = day_bounds(day)
    tables = build(conn, T.DAILY, key, {"start": start, "end": end})
    conn.rollback()
    fails = quality.check_tables(tables)
    if fails:
        raise QualityError(f"dia {day}", fails)
    return publish(tables, out, f"dt={day.isoformat()}")


def extract_snapshots(conn, snap_date, out, key):
    tables = build(conn, T.SNAPSHOT, key)
    conn.rollback()
    fails = quality.check_tables(tables)
    if fails:
        raise QualityError("fotografia das dimensões", fails)
    return publish(tables, out, f"snapshot={snap_date.isoformat()}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", help="primeiro dia a extrair (AAAA-MM-DD); padrão: 2 dias atrás")
    ap.add_argument("--include-today", action="store_true", help="inclui o dia de hoje (parcial)")
    ap.add_argument("--out", default=os.environ.get("EXTRACT_OUT", "/out"))
    a = ap.parse_args(argv)

    key = pseudo.load_key()
    now = dt.datetime.now(TZ)
    today = now.date()
    first = dt.date.fromisoformat(a.since) if a.since else today - dt.timedelta(days=2)
    last = today if a.include_today else today - dt.timedelta(days=1)
    if first > last:
        print("Nada a extrair: --since está depois do último dia completo.", file=sys.stderr)
        return 1

    run = {"started_at": now.astimezone(dt.timezone.utc).isoformat(), "pseudo_key_id": pseudo.key_id(key),
           "status": "ok", "errors": [], "days": {}}
    conn = connect(os.environ["DATABASE_URL"])
    try:
        day = first
        while day <= last:
            run["days"][day.isoformat()] = extract_day(conn, day, a.out, key)
            day += dt.timedelta(days=1)
        run["snapshot"] = {"date": today.isoformat(), "rows": extract_snapshots(conn, today, a.out, key)}
    except QualityError as e:
        run["status"], run["errors"], run["failed_at"] = "failed", e.failures, e.label
    finally:
        conn.close()

    finished = dt.datetime.now(dt.timezone.utc)
    run["finished_at"] = finished.isoformat()
    runs = os.path.join(a.out, "_runs")
    os.makedirs(runs, exist_ok=True)
    with open(os.path.join(runs, finished.strftime("%Y%m%dT%H%M%SZ") + ".json"), "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0 if run["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
