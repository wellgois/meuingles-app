#!/usr/bin/env bash
# Chamado só pelo Airflow via SSH (chave restrita). Aceita apenas "extract" ou "upload".
set -euo pipefail
case "${SSH_ORIGINAL_COMMAND:-}" in
  extract) exec /opt/meuingles/data-platform/run_extract.sh ;;
  upload)  exec /opt/meuingles/data-platform/run_upload.sh ;;
  *) echo "comando não permitido" >&2; exit 2 ;;
esac
