#!/usr/bin/env bash
# Extrai e envia ao lake. Agendado pelo cron (temporário, até o job do Databricks assumir).
set -uo pipefail
cd /opt/meuingles/data-platform
LOG=/opt/meuingles-data/_logs/daily.log
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date -Is) ==="
  if ./run_extract.sh && ./run_upload.sh; then echo "status=ok"; else echo "status=FALHOU"; fi
} >> "$LOG" 2>&1
if tail -n 1 "$LOG" | grep -q "status=FALHOU"; then
  ./notify_failure.sh >> "$LOG" 2>&1 || true
fi
