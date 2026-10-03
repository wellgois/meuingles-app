#!/usr/bin/env bash
# Envia ao lake o que o extrator gravou. Uso: ./run_upload.sh [--dry-run] [--all] [--hours N]
set -euo pipefail
cd /opt/meuingles/data-platform
[ -s /opt/meuingles-data/lake.sas ] || { echo "Falta /opt/meuingles-data/lake.sas" >&2; exit 1; }
exec docker compose --env-file /opt/meuingles/.env run --rm -T upload "$@"
