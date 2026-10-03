import importlib.util
import pathlib

import pytest

pytest.importorskip("airflow")
pytest.importorskip("airflow.providers.ssh")

DAG_FILE = pathlib.Path(__file__).resolve().parents[2] / "orchestration" / "dags" / "meuingles_daily.py"


@pytest.fixture(scope="module")
def dag():
    spec = importlib.util.spec_from_file_location("meuingles_daily", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.dag


def test_dag_basica(dag):
    assert dag.dag_id == "meuingles_daily"
    assert set(dag.task_dict) == {"extract", "upload"}
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_ordem_extrair_depois_enviar(dag):
    assert dag.get_task("upload").upstream_task_ids == {"extract"}
    assert dag.get_task("extract").upstream_task_ids == set()


def test_retentativas_e_tempo_limite(dag):
    for task_id in ("extract", "upload"):
        task = dag.get_task(task_id)
        assert task.retries == 2
        assert task.execution_timeout is not None


def test_comandos_so_extract_e_upload(dag):
    assert dag.get_task("extract").command == "extract"
    assert dag.get_task("upload").command == "upload"
