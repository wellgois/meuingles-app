# Orchestration (Airflow DAG and Prefect flow)

`dags/meuingles_daily.py` is the Airflow version of the daily pipeline that cron runs today:
`extract` (Postgres -> pseudonymized Parquet) then `upload` (Parquet -> ADLS Gen2 landing).

- The tasks run on the VPS over SSH. The SSH key is restricted in `authorized_keys` to
  `pipeline_step.sh`, which accepts only the words `extract` and `upload` (anything else exits with code 2).
- CI (job `airflow`) checks that the DAG imports, the task order, retries, timeouts and the allowed commands.
- Production scheduling stays on cron until the Databricks job takes over; Airflow is started on demand.

## Prefect flow

`prefect_flow.py` is the same pipeline as a Prefect flow: tasks `extract` and `upload` in that order, 2 retries
with a 10-minute wait, a 45-minute limit per step, and the same restricted SSH key and `pipeline_step.sh`.
The flow refuses any step outside `extract` and `upload` before opening a connection, and `upload` never runs if
`extract` fails.

```bash
export MEUINGLES_SSH_TARGET=usuario@host MEUINGLES_SSH_KEY=/caminho/da/chave
python orchestration/prefect_flow.py           # one run
python orchestration/prefect_flow.py --serve   # daily at 06:30 UTC, like the DAG
```

CI (job `prefect`) runs the flow with a simulated SSH and a temporary Prefect database: step order, retries and
limits, the allow-list, no upload after a failed extract, and no SSH call without configuration.
