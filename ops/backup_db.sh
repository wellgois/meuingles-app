#!/usr/bin/env bash
# Backup do Postgres: dump -> gzip -> gpg (AES256). Guarda os 7 últimos.
set -uo pipefail
DIR=/root/backups-db; PASS=/root/secrets/backup.pass; LOG=/opt/meuingles-data/_logs/backup.log
umask 077; mkdir -p "$DIR" "$(dirname "$LOG")"
run() {
  [ -s "$PASS" ] || { echo "falta $PASS"; return 1; }
  local f="$DIR/meuingles-$(date -u +%Y%m%dT%H%M%SZ).sql.gz.gpg"
  cd /opt/meuingles || return 1
  docker compose exec -T db pg_dump -U meuingles --no-owner meuingles | gzip -9 \
    | gpg --batch --yes --pinentry-mode loopback --passphrase-file "$PASS" --compress-algo none --symmetric --cipher-algo AES256 -o "$f.tmp" \
    || { rm -f "$f.tmp"; echo "dump ou criptografia falhou"; return 1; }
  [ "$(stat -c %s "$f.tmp")" -gt 500 ] || { rm -f "$f.tmp"; echo "arquivo pequeno demais"; return 1; }
  mv "$f.tmp" "$f"; echo "backup: $(basename "$f") $(stat -c %s "$f") bytes"
  ls -1t "$DIR"/meuingles-*.sql.gz.gpg 2>/dev/null | tail -n +8 | xargs -r rm -f
}
{ echo "=== $(date -Is) ==="; if run; then echo "status=ok"; else echo "status=FALHOU"; fi; } >> "$LOG" 2>&1
if tail -n 1 "$LOG" | grep -q "status=FALHOU"; then
  NOTIFY_LOG="$LOG" NOTIFY_SUBJECT="MeuInglês: o backup do banco falhou" /opt/meuingles/data-platform/notify_failure.sh >> "$LOG" 2>&1
fi
exit 0
