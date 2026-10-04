#!/usr/bin/env bash
# Teste de restauração: decifra o último backup, restaura num Postgres descartável e compara contagens.
set -uo pipefail
F="${1:-$(ls -1t /root/backups-db/meuingles-*.sql.gz.gpg 2>/dev/null | head -n 1)}"
[ -n "$F" ] && [ -s "$F" ] || { echo "nenhum backup"; exit 1; }
N="pgrestore-$$"; trap 'docker rm -f "$N" >/dev/null 2>&1' EXIT
docker run -d --rm --name "$N" -e POSTGRES_PASSWORD=r -e POSTGRES_DB=r postgres:16-alpine >/dev/null || exit 1
for i in $(seq 1 40); do docker exec "$N" pg_isready -U postgres -d r >/dev/null 2>&1 && break; sleep 1; done
gpg --batch --pinentry-mode loopback --passphrase-file /root/secrets/backup.pass --decrypt "$F" 2>/dev/null | gunzip \
  | docker exec -i "$N" psql -U postgres -d r -v ON_ERROR_STOP=1 -q >/dev/null || { echo "RESTAURAÇÃO FALHOU"; exit 1; }
Q="select 'users', count(*) from users union all select 'attempts', count(*) from attempts union all select 'interview_sessions', count(*) from interview_sessions"
echo "--- restaurado:"; docker exec "$N" psql -U postgres -d r -Atc "$Q"
echo "--- produção:"; cd /opt/meuingles && docker compose exec -T db psql -U meuingles -d meuingles -Atc "$Q"
echo "RESTAURAÇÃO OK"
