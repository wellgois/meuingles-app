"""MeuInglês: pipeline diário. Extrai do Postgres (Parquet pseudonimizado) e envia ao lake (ADLS Gen2).

Os dois passos rodam na VPS por SSH, com uma chave restrita ao script orchestration/pipeline_step.sh,
que só aceita "extract" e "upload". Em produção o agendamento ainda é do cron; esta DAG é o equivalente
versionado e testado, pronto para quando o Airflow for ligado.
"""
import os
from datetime import timedelta

import pendulum
from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.sdk import DAG

SSH_CONN_ID = os.environ.get("MEUINGLES_SSH_CONN_ID", "meuingles_vps")

default_args = {
    "owner": "wellgois",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(minutes=45),
}

with DAG(
    dag_id="meuingles_daily",
    description="Extrai do Postgres e envia ao lake (landing)",
    schedule="30 6 * * *",
    start_date=pendulum.datetime(2026, 10, 4, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["meuingles", "lake"],
) as dag:
    extract = SSHOperator(task_id="extract", ssh_conn_id=SSH_CONN_ID, command="extract", cmd_timeout=1800)
    upload = SSHOperator(task_id="upload", ssh_conn_id=SSH_CONN_ID, command="upload", cmd_timeout=1800)
    extract >> upload
