import json
import os
import time

import pytest

from extractor import upload


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def upload_blob(self, name, data, overwrite=False):
        assert overwrite is True
        self.blobs[name] = data.read()


FILES = {
    "attempts/dt=2026-10-03/part-0.parquet": b"A",
    "users/snapshot=2026-10-03/part-0.parquet": b"U",
    "_runs/20261003T120000Z.json": b"{}",
    "pseudo.key": b"SEGREDO-CHAVE",
    "lake.sas": b"https://conta.blob.core.windows.net/c?sig=SEGREDO-SAS",
    "attempts/dt=2026-10-03/.part-0.parquet.tmp": b"T",
    "attempts/dt=2026-10-03/extra.txt": b"E",
    "_logs/daily.log": b"L",
}
EXPECTED = {
    "landing/attempts/dt=2026-10-03/part-0.parquet",
    "landing/users/snapshot=2026-10-03/part-0.parquet",
    "landing/_runs/20261003T120000Z.json",
}


@pytest.fixture()
def tree(tmp_path):
    for rel, content in FILES.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return tmp_path


def test_so_o_permitido_sobe_e_segredos_ficam(tree):
    c = FakeContainer()
    r = upload.upload(c, str(tree), "landing", everything=True)
    assert set(c.blobs) == EXPECTED
    assert r["files"] == 3
    assert b"SEGREDO" not in b"".join(c.blobs.values())


def test_janela_de_horas(tree):
    old = time.time() - 10 * 86400
    p = tree / "attempts/dt=2026-10-03/part-0.parquet"
    os.utime(p, (old, old))
    c = FakeContainer()
    upload.upload(c, str(tree), "landing", hours=72)
    assert "landing/attempts/dt=2026-10-03/part-0.parquet" not in c.blobs
    assert "landing/users/snapshot=2026-10-03/part-0.parquet" in c.blobs
    c2 = FakeContainer()
    upload.upload(c2, str(tree), "landing", everything=True)
    assert "landing/attempts/dt=2026-10-03/part-0.parquet" in c2.blobs


def test_dry_run_nao_envia(tree):
    c = FakeContainer()
    r = upload.upload(c, str(tree), "landing", everything=True, dry_run=True)
    assert c.blobs == {} and set(r["names"]) == EXPECTED


@pytest.mark.parametrize("rel,ok", [
    ("attempts/dt=2026-10-03/part-0.parquet", True),
    ("_runs/x.json", True),
    ("pseudo.key", False),
    ("lake.sas", False),
    ("_logs/daily.log", False),
    ("a/b/c/part-0.parquet", False),
    ("a/b/part-1.parquet", False),
    ("a/.b/part-0.parquet", False),
    ("_runs/sub/x.json", False),
    ("../x/part-0.parquet", False),
])
def test_lista_de_permissao(rel, ok):
    assert upload.allowed(rel) is ok


def test_sas_invalida(monkeypatch):
    monkeypatch.delenv("LAKE_SAS_FILE", raising=False)
    monkeypatch.delenv("LAKE_SAS_URL", raising=False)
    with pytest.raises(RuntimeError):
        upload.load_sas_url()
    monkeypatch.setenv("LAKE_SAS_URL", "http://inseguro/c?sig=x")
    with pytest.raises(RuntimeError):
        upload.load_sas_url()


def test_sas_de_arquivo(monkeypatch, tmp_path):
    f = tmp_path / "s"
    f.write_text("https://conta.blob.core.windows.net/c?sv=1&sig=abc\n")
    monkeypatch.delenv("LAKE_SAS_URL", raising=False)
    monkeypatch.setenv("LAKE_SAS_FILE", str(f))
    assert upload.load_sas_url().endswith("sig=abc")


def test_main_dry_run(tree, capsys, monkeypatch):
    monkeypatch.delenv("LAKE_SAS_URL", raising=False)
    monkeypatch.delenv("LAKE_SAS_FILE", raising=False)
    assert upload.main(["--dry-run", "--all", "--root", str(tree)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and set(out["names"]) == EXPECTED
