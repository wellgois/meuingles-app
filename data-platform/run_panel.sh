#!/usr/bin/env bash
# Gera a página pública da evolução (HTML estático) a partir dos Parquet do extrator. Sem Spark, sem custo.
set -euo pipefail
OUT=/var/www/meuingles-evolucao
mkdir -p "$OUT"
if ! docker image inspect meuingles-gold >/dev/null 2>&1; then
  echo "painel: imagem meuingles-gold ausente, reconstruindo" >&2
  docker build -q -f /opt/meuingles/data-platform/Dockerfile.gold -t meuingles-gold /opt/meuingles/data-platform >&2
fi
exec docker run --rm -e PYTHONDONTWRITEBYTECODE=1 \
  -v /opt/meuingles:/repo:ro -v /opt/meuingles-data:/out:ro -v "$OUT":/public \
  -w /repo/data-platform meuingles-gold python -m panel.build --data /out --out /public/index.html "$@"
