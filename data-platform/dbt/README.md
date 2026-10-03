# MeuInglês gold layer (dbt)

Six gold models on top of the silver Delta tables: daily progress per user, hardest phonemes,
days to advance a level, signup funnel by source/campaign, weekly retention and daily cost.

## Run locally (free): DuckDB
`../run_gold_local.sh` rebuilds landing -> bronze -> silver (Spark/Delta) in a temp folder, loads silver
into DuckDB with `lake/load_duckdb.py`, and runs `dbt build --target local`.
The output (`/opt/meuingles-gold-local/meuingles.duckdb`) holds pseudonymized per-user rows: delete it when done.

## Switch to Databricks (when the workspace is upgraded)
1. Register the silver Delta folders as tables in a Unity Catalog schema named `silver`
   (`CREATE TABLE ... USING DELTA LOCATION 'abfss://<container>@<account>.dfs.core.windows.net/silver/<table>'`).
2. `pip install dbt-databricks` and export `DBT_DATABRICKS_HOST`, `DBT_DATABRICKS_HTTP_PATH`,
   `DBT_DATABRICKS_TOKEN` (and optionally `DBT_DATABRICKS_CATALOG`).
3. `dbt build --profiles-dir . --target databricks`.

Only two macros differ between engines (`days_between`, `week_start`, in `macros/portable.sql`).
The `default__` (Spark SQL) versions are exercised only after the upgrade; the DuckDB ones are covered by CI.
