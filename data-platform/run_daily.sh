#!/usr/bin/env bash
# Extrai, envia ao lake e atualiza o painel público. Agendado pelo cron (temporário, até o job do Databricks assumir).
set -uo pipefail
cd /opt/meuingles/data-platform
LOG=/opt/meuingles-data/_logs/daily.log
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date -Is) ==="
  if ./run_extract.sh && ./run_upload.sh; then STATUS=ok; else STATUS=FALHOU; fi
  if [ "$STATUS" = ok ]; then ./run_panel.sh || echo "painel: falhou (não afeta o envio ao lake)"; fi
  echo "status=$STATUS"
} >> "$LOG" 2>&1
if tail -n 1 "$LOG" | grep -q "status=FALHOU"; then
  ./notify_failure.sh >> "$LOG" 2>&1 || true
fi
