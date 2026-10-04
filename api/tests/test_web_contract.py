"""Elementos que o JavaScript do app usa na inicialização precisam existir no HTML (um ausente quebra o app inteiro)."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


def test_ids_estaticos_usados_no_carregamento():
    html = (WEB / "app" / "index.html").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    for ident in ("goStar", "ivBox", "cvBox"):
        assert f'id="{ident}"' in html, ident
        assert ident in js, ident
