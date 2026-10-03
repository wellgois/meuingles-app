# Orchestration (Airflow DAG)

`dags/meuingles_daily.py` is the Airflow version of the daily pipeline that cron runs today:
`extract` (Postgres -> pseudonymized Parquet) then `upload` (Parquet -> ADLS Gen2 landing).

- The tasks run on the VPS over SSH. The SSH key is restricted in `authorized_keys` to
  `pipeline_step.sh`, which accepts only the words `extract` and `upload` (anything else exits with code 2).
- CI (job `airflow`) checks that the DAG imports, the task order, retries, timeouts and the allowed commands.
- Production scheduling stays on cron until the Databricks job takes over; Airflow is started on demand.
