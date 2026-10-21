import importlib.util
import pathlib
import subprocess

import pytest

pytest.importorskip("prefect")

from prefect.testing.utilities import prefect_test_harness  # noqa: E402

FLOW_FILE = pathlib.Path(__file__).resolve().parents[2] / "orchestration" / "prefect_flow.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("prefect_flow", FLOW_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", autouse=True)
def banco_prefect_temporario():
    with prefect_test_harness():
        yield


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv("MEUINGLES_SSH_TARGET", "pipeline@vps.example")
    monkeypatch.setenv("MEUINGLES_SSH_KEY", "/tmp/chave-teste")


@pytest.fixture
def ssh_falso(mod, monkeypatch):
    """Troca o subprocess.run por um registrador; devolve a lista de comandos executados."""
    chamadas = []
    codigos = {}

    def falso(comando, **kwargs):
        chamadas.append(comando)
        return subprocess.CompletedProcess(comando, codigos.get(comando[-1], 0), stdout="ok", stderr="erro simulado")

    monkeypatch.setattr(mod.subprocess, "run", falso)
    # Sem espera real entre tentativas nos testes.
    monkeypatch.setattr(mod, "extract", mod.extract.with_options(retries=0))
    monkeypatch.setattr(mod, "upload", mod.upload.with_options(retries=0))
    return chamadas, codigos


def test_passos_permitidos_sao_so_extract_e_upload(mod):
    assert mod.PASSOS_PERMITIDOS == ("extract", "upload")


@pytest.mark.parametrize("passo", ["", "bash", "extract; id", "upload && id", "../extract", "EXTRACT"])
def test_comando_fora_da_lista_e_recusado(mod, passo):
    with pytest.raises(ValueError):
        mod.montar_comando_ssh(passo, "pipeline@vps.example", "/tmp/chave")


def test_comando_ssh_usa_chave_restrita_e_sem_senha(mod):
    cmd = mod.montar_comando_ssh("extract", "pipeline@vps.example", "/tmp/chave")
    assert cmd[0] == "ssh"
    assert cmd[-2:] == ["pipeline@vps.example", "extract"]
    assert "IdentitiesOnly=yes" in cmd
    assert "BatchMode=yes" in cmd


def test_retentativas_e_tempo_limite_iguais_aos_da_dag(mod):
    assert mod.CRON_DIARIO == "30 6 * * *"
    for passo in (mod.extract, mod.upload):
        assert passo.retries == 2
        assert passo.retry_delay_seconds == 600
        assert passo.timeout_seconds == 45 * 60


def test_flow_roda_extract_e_depois_upload(mod, ambiente, ssh_falso):
    chamadas, _ = ssh_falso
    mod.meuingles_daily()
    assert [c[-1] for c in chamadas] == ["extract", "upload"]


def test_se_extract_falha_o_upload_nao_roda(mod, ambiente, ssh_falso):
    chamadas, codigos = ssh_falso
    codigos["extract"] = 1
    with pytest.raises(Exception):
        mod.meuingles_daily()
    assert [c[-1] for c in chamadas] == ["extract"]


def test_sem_configuracao_o_flow_falha_antes_de_chamar_ssh(mod, ssh_falso, monkeypatch):
    chamadas, _ = ssh_falso
    monkeypatch.delenv("MEUINGLES_SSH_TARGET", raising=False)
    monkeypatch.delenv("MEUINGLES_SSH_KEY", raising=False)
    with pytest.raises(Exception):
        mod.meuingles_daily()
    assert chamadas == []
