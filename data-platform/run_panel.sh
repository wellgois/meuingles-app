#!/usr/bin/env bash
# Gera a página pública da evolução (HTML estático) a partir dos Parquet do extrator. Sem Spark, sem custo.
set -euo pipefail
OUT=/var/www/meuingles-evolucao
mkdir -p "$OUT"
exec docker run --rm -e PYTHONDONTWRITEBYTECODE=1 \
  -v /opt/meuingles:/repo:ro -v /opt/meuingles-data:/out:ro -v "$OUT":/public \
  -w /repo/data-platform meuingles-gold python -m panel.build --data /out --out /public/index.html "$@"
