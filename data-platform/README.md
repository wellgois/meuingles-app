# MeuInglês data platform

Daily extract of the app database (PostgreSQL, OLTP) into pseudonymized Parquet files.
This is the landing layer for the bronze/silver/gold pipeline (ADLS Gen2, Databricks, Delta Lake, dbt).

## What leaves the database
- Attempts: scores, durations, token usage. Never transcripts, feedback text or raw JSON.
- Word and phoneme rows only for levels 1-2 (fixed exercises). Free speech (levels 3-4) stays out.
- Users: plan, level, track, signup source. Never name, e-mail or payment data.
- IDs (user, browser, session) are replaced by HMAC-SHA256; the key never leaves the server.
- `deleted_users`: suppression list so deleted accounts are also removed downstream.

## Layout
`<out>/<table>/dt=YYYY-MM-DD/part-0.parquet` (daily facts) and `<out>/<table>/snapshot=YYYY-MM-DD/part-0.parquet` (dimensions).
Each run writes a manifest in `<out>/_runs/`. Quality checks run before anything is written.

## Run
`./run_extract.sh` (yesterday and the day before) or `./run_extract.sh --since 2026-10-01 --include-today`.
