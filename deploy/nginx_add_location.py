"""Insere o bloco /meuingles/ no server block de wellgois.com.

Uso: python3 nginx_add_location.py <arquivo.conf> <porta> <dominio>
Saída: 0 = alterado, 3 = já existia, 4 = nenhum server block encontrado.
"""
import re
import sys

path, port, domain = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()

if re.search(r"location\s+(\^~\s+)?/meuingles", text):
    print("O bloco /meuingles já existe neste arquivo.")
    sys.exit(3)


def server_blocks(src):
    """Devolve (inicio, fim) de cada 'server { ... }' de nível superior, ignorando comentários e aspas."""
    blocks, depth, i, n = [], 0, 0, len(src)
    start = None
    while i < n:
        c = src[i]
        if c == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c in "\"'":
            q = c; i += 1
            while i < n and src[i] != q:
                i += 2 if src[i] == "\\" else 1
            i += 1
            continue
        if c == "{":
            head = src[max(0, i - 40):i]
            if start is None and re.search(r"(^|[\s;}])server\s*$", head):
                start = (i, depth)
            depth += 1
        elif c == "}":
            depth -= 1
            if start is not None and depth == start[1]:
                blocks.append((start[0], i))
                start = None
        i += 1
    return blocks


dom = re.escape(domain)
cands = []
for a, b in server_blocks(text):
    body = text[a:b]
    names = re.findall(r"server_name\s+([^;]+);", body)
    if not any(re.search(r"(^|\s)" + dom + r"(\s|$)", nm) for nm in names):
        continue
    is_ssl = bool(re.search(r"listen\s+[^;]*443", body))
    redirect_only = bool(re.search(r"^\s*return\s+30[12]", body, re.M)) and "location" not in body
    cands.append((a, b, is_ssl, redirect_only))

targets = [c for c in cands if c[2]] or [c for c in cands if not c[3]]
if not targets:
    print("Nenhum server block com server_name " + domain + " encontrado.")
    sys.exit(4)

block = f"""
    # MeuInglês (adicionado pelo instalador)
    location = /meuingles {{ return 301 /meuingles/; }}
    location ^~ /meuingles/ {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        client_max_body_size 5m;
    }}
"""
for a, b, *_ in sorted(targets, key=lambda t: -t[1]):
    text = text[:b] + block + text[b:]
open(path, "w", encoding="utf-8").write(text)
print(f"Bloco /meuingles/ inserido em {len(targets)} server block(s) " + ("HTTPS." if targets[0][2] else "HTTP."))
sys.exit(0)
