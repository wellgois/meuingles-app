#!/usr/bin/env bash
# Extrai o dia anterior e relê o anterior a ele (visitas podem ser atualizadas depois). Usado pelo cron.
set -euo pipefail
cd /opt/meuingles/data-platform
exec docker compose --env-file /opt/meuingles/.env run --rm -T extract "$@"
