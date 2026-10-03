"""Envia ao lake (ADLS Gen2) o que o extrator gravou. Só Parquet e manifestos entram; chaves e logs nunca."""
import argparse
import json
import os
import time


def allowed(rel: str) -> bool:
    """Lista de permissão: <tabela>/<partição>/part-0.parquet e _runs/<arquivo>.json. O resto fica de fora."""
    parts = rel.split("/")
    if any(p == "" or p.startswith(".") for p in parts):
        return False
    if parts[0] == "_runs":
        return len(parts) == 2 and parts[1].endswith(".json")
    return len(parts) == 3 and parts[2] == "part-0.parquet"


def candidates(root, everything, cutoff):
    found = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            path = os.path.join(dirpath, n)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if not allowed(rel):
                continue
            if not everything and os.path.getmtime(path) < cutoff:
                continue
            found.append((rel, path))
    return sorted(found)


def upload(container, root, prefix="landing", everything=False, hours=72, dry_run=False, now=None):
    cutoff = (time.time() if now is None else now) - hours * 3600
    names, total = [], 0
    for rel, path in candidates(root, everything, cutoff):
        name = f"{prefix}/{rel}" if prefix else rel
        if not dry_run:
            with open(path, "rb") as f:
                container.upload_blob(name, f, overwrite=True)
        names.append(name)
        total += os.path.getsize(path)
    return {"dry_run": dry_run, "files": len(names), "bytes": total, "names": names}


def load_sas_url() -> str:
    url = os.environ.get("LAKE_SAS_URL", "").strip()
    path = os.environ.get("LAKE_SAS_FILE")
    if not url and path:
        with open(path, encoding="utf-8") as f:
            url = f.read().strip()
    if not url.startswith("https://") or "?" not in url:
        raise RuntimeError("URL SAS do contêiner ausente ou inválida.")
    return url


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", dest="everything", help="envia tudo (primeira carga)")
    ap.add_argument("--hours", type=int, default=72, help="envia só arquivos alterados nas últimas N horas")
    ap.add_argument("--dry-run", action="store_true", help="só lista o que seria enviado")
    ap.add_argument("--root", default=os.environ.get("EXTRACT_OUT", "/out"))
    ap.add_argument("--prefix", default=os.environ.get("LAKE_PREFIX", "landing"))
    a = ap.parse_args(argv)

    container = None
    if not a.dry_run:
        from azure.storage.blob import ContainerClient  # import tardio: os testes não precisam do SDK
        container = ContainerClient.from_container_url(load_sas_url())
    result = upload(container, a.root, a.prefix, a.everything, a.hours, a.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
