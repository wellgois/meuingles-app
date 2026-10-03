#!/usr/bin/env bash
# Avisa por e-mail (SMTP do app) quando o pipeline diário falha. Uso: ./notify_failure.sh [--test]
set -uo pipefail
LOG=/opt/meuingles-data/_logs/daily.log
SUBJECT="MeuInglês: o pipeline diário falhou"
[ "${1:-}" = "--test" ] && SUBJECT="[TESTE] $SUBJECT"
TAIL_TXT="$(tail -n 25 "$LOG" 2>/dev/null | sed -E 's#https://[^ ]*\?[^ ]*#[URL omitida]#g')"
cd /opt/meuingles
docker compose exec -T -e SUBJECT="$SUBJECT" -e MSG="$TAIL_TXT" api python -c "
import os
from app import mailer
to = os.environ.get('CONTACT_EMAIL')
lines = ['Últimas linhas do log do pipeline diário:'] + os.environ.get('MSG', '').splitlines()[-25:]
ok = bool(to) and mailer.configured() and mailer.send(to, os.environ['SUBJECT'], lines)
print('e-mail enviado' if ok else 'e-mail NÃO enviado')
"
