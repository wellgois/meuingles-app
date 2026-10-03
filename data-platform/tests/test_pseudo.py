import pytest

from extractor import pseudo

KEY = b"k" * 32


def test_deterministico_e_sem_vazar():
    uid = "123e4567-e89b-12d3-a456-426614174000"
    a = pseudo.pseudo(KEY, uid)
    assert a == pseudo.pseudo(KEY, uid)
    assert len(a) == 32 and "123e4567" not in a


def test_chaves_diferentes_geram_valores_diferentes():
    assert pseudo.pseudo(KEY, "x") != pseudo.pseudo(b"z" * 32, "x")


def test_none():
    assert pseudo.pseudo(KEY, None) is None


def test_load_key_exige_tamanho(monkeypatch):
    monkeypatch.delenv("PSEUDO_KEY_FILE", raising=False)
    monkeypatch.setenv("PSEUDO_KEY", "curta")
    with pytest.raises(RuntimeError):
        pseudo.load_key()
    monkeypatch.setenv("PSEUDO_KEY", "a" * 40)
    assert pseudo.load_key() == b"a" * 40


def test_load_key_de_arquivo(monkeypatch, tmp_path):
    f = tmp_path / "k"
    f.write_text("b" * 40 + "\n")
    monkeypatch.delenv("PSEUDO_KEY", raising=False)
    monkeypatch.setenv("PSEUDO_KEY_FILE", str(f))
    assert pseudo.load_key() == b"b" * 40
