#!/usr/bin/env bash
# Pipeline completo local e sem custo: landing -> bronze -> silver (Spark/Delta) -> DuckDB -> gold (dbt).
# Uso: ./run_gold_local.sh [DATA_INICIAL]   (padrão: 2026-10-01)
set -euo pipefail
FROM="${1:-2026-10-01}"
TO="$(TZ=America/Sao_Paulo date +%F)"
LAKE=/opt/meuingles-lake-local
OUT=/opt/meuingles-gold-local
cd /opt/meuingles/data-platform
rm -rf "$LAKE" "$OUT"
mkdir -p "$LAKE" "$OUT"
trap 'rm -rf "$LAKE"' EXIT   # o bronze/silver temporário nunca fica no disco

docker run --rm -v /opt/meuingles:/repo -v "$LAKE":/lake -v /opt/meuingles-data:/lake/landing:ro \
  -w /repo/data-platform meuingles-lake-test python -m lake.run --root /lake --from "$FROM" --to "$TO"

docker run --rm -v /opt/meuingles:/repo -v "$LAKE":/lake:ro -v "$OUT":/out -w /repo/data-platform \
  -e DBT_SEND_ANONYMOUS_USAGE_STATS=false -e DBT_DUCKDB_PATH=/out/meuingles.duckdb \
  -e DBT_TARGET_PATH=/tmp/dbt-target -e DBT_LOG_PATH=/tmp/dbt-logs meuingles-gold \
  sh -c "python -m lake.load_duckdb --silver /lake/silver --db /out/meuingles.duckdb && cd dbt && dbt build --profiles-dir . --target local"

docker run --rm -v "$OUT":/out meuingles-gold python -c "
import duckdb
con = duckdb.connect('/out/meuingles.duckdb', read_only=True)
for t in ['gold_user_daily_progress', 'gold_phoneme_difficulty', 'gold_level_progression',
          'gold_funnel_by_source', 'gold_weekly_retention', 'gold_daily_cost']:
    print(t, con.execute(f'select count(*) from gold.{t}').fetchone()[0], 'linhas')
print('fonemas mais difíceis:', con.execute('select phoneme, attempts, avg_score from gold.gold_phoneme_difficulty order by avg_score limit 5').fetchall())
print('custo por dia:', con.execute('select attempt_date, azure_cost_usd, llm_cost_usd, total_cost_usd from gold.gold_daily_cost order by attempt_date').fetchall())
"
