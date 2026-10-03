#!/usr/bin/env bash
# Chamado pelo GitHub Actions (a chave SSH só consegue rodar este script).
set -euo pipefail
cd /opt/meuingles
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Há alterações não commitadas na VPS: deploy cancelado." >&2
  exit 1
fi
PREV=$(git rev-parse HEAD)
git fetch --quiet origin main
git merge --ff-only origin/main
PORT=$(grep -m1 '^APP_PORT=' .env | cut -d= -f2)
docker compose up -d --build
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/health" >/dev/null; then
    echo "deploy ok: $(git rev-parse --short HEAD)"
    exit 0
  fi
done
echo "Health check falhou; voltando para $PREV" >&2
git reset --hard "$PREV"
docker compose up -d --build
exit 1
