"""MeuInglês: pipeline diário em Prefect. Extrai do Postgres (Parquet pseudonimizado) e envia ao lake (ADLS Gen2).

Equivalente em Prefect da DAG de Airflow (dags/meuingles_daily.py): os mesmos dois passos, na mesma ordem, rodando
na VPS por SSH com a chave restrita ao script orchestration/pipeline_step.sh, que só aceita "extract" e "upload".
Em produção o agendamento continua sendo do cron; este flow é a versão versionada e testada, pronta para quando
o Prefect for ligado.

Configuração por variáveis de ambiente (nenhum segredo vai para o Git):
    MEUINGLES_SSH_TARGET   usuario@host da VPS (obrigatória)
    MEUINGLES_SSH_KEY      caminho da chave privada restrita (obrigatória)

Rodar uma vez:   python orchestration/prefect_flow.py
Agendar (serve): python orchestration/prefect_flow.py --serve
"""
import os
import subprocess
import sys

from prefect import flow, get_run_logger, task

# Os únicos comandos que o flow aceita. O script do lado da VPS repete esta lista (defesa em duas camadas).
PASSOS_PERMITIDOS = ("extract", "upload")

CRON_DIARIO = "30 6 * * *"  # UTC, igual à DAG de Airflow
TENTATIVAS = 2
ESPERA_ENTRE_TENTATIVAS_S = 600
LIMITE_POR_PASSO_S = 45 * 60
LIMITE_SSH_S = 1800


def montar_comando_ssh(passo: str, destino: str, chave: str) -> list[str]:
    """Monta o comando ssh. Recusa qualquer passo fora da lista, antes de tocar na rede."""
    if passo not in PASSOS_PERMITIDOS:
        raise ValueError(f"passo não permitido: {passo!r}")
    return [
        "ssh",
        "-i", chave,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        destino,
        passo,
    ]


def _configuracao() -> tuple[str, str]:
    destino = os.environ.get("MEUINGLES_SSH_TARGET", "")
    chave = os.environ.get("MEUINGLES_SSH_KEY", "")
    if not destino or not chave:
        raise RuntimeError("defina MEUINGLES_SSH_TARGET e MEUINGLES_SSH_KEY")
    return destino, chave


def executar_passo(passo: str) -> None:
    destino, chave = _configuracao()
    comando = montar_comando_ssh(passo, destino, chave)
    resultado = subprocess.run(comando, capture_output=True, text=True, timeout=LIMITE_SSH_S)
    logger = get_run_logger()
    if resultado.stdout:
        logger.info(resultado.stdout.strip())
    if resultado.returncode != 0:
        # A saída de erro vem do script da VPS; nunca inclui a chave nem variáveis de ambiente.
        raise RuntimeError(f"passo {passo} falhou (código {resultado.returncode}): {resultado.stderr.strip()}")


@task(retries=TENTATIVAS, retry_delay_seconds=ESPERA_ENTRE_TENTATIVAS_S, timeout_seconds=LIMITE_POR_PASSO_S)
def extract() -> None:
    executar_passo("extract")


@task(retries=TENTATIVAS, retry_delay_seconds=ESPERA_ENTRE_TENTATIVAS_S, timeout_seconds=LIMITE_POR_PASSO_S)
def upload() -> None:
    executar_passo("upload")


@flow(name="meuingles_daily", description="Extrai do Postgres e envia ao lake (landing)")
def meuingles_daily() -> None:
    # Chamadas sequenciais: se a extração falhar depois das tentativas, o envio nem começa.
    extract()
    upload()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        meuingles_daily.serve(name="meuingles-daily", cron=CRON_DIARIO, tags=["meuingles", "lake"])
    else:
        meuingles_daily()
