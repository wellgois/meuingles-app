#!/usr/bin/env bash
# Extrai e envia ao lake. Agendado pelo cron (temporário, até o Airflow assumir na etapa 3.4).
set -uo pipefail
cd /opt/meuingles/data-platform
LOG=/opt/meuingles-data/_logs/daily.log
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date -Is) ==="
  if ./run_extract.sh && ./run_upload.sh; then echo "status=ok"; else echo "status=FALHOU"; fi
} >> "$LOG" 2>&1
