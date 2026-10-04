import pytest

from app import crypto


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("CV_KEY", "cd" * 32)


def test_ida_e_volta():
    assert crypto.decrypt(crypto.encrypt(b"segredo", b"a"), b"a") == b"segredo"


def test_nonce_diferente_a_cada_vez():
    assert crypto.encrypt(b"x") != crypto.encrypt(b"x")


def test_contexto_diferente_falha():
    blob = crypto.encrypt(b"x", b"usuario-1")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(blob, b"usuario-2")


def test_adulteracao_falha():
    blob = bytearray(crypto.encrypt(b"x"))
    blob[-1] ^= 1
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(bytes(blob))


def test_dado_curto_ou_de_outra_versao_falha():
    for blob in (b"abc", b"\x09" + b"0" * 40):
        with pytest.raises(crypto.CryptoError):
            crypto.decrypt(blob)


def test_sem_chave(monkeypatch):
    monkeypatch.delenv("CV_KEY")
    monkeypatch.setattr(crypto, "KEY_FILE", "/nonexistent/cv.key")
    assert crypto.ready() is False
    with pytest.raises(crypto.CryptoError):
        crypto.encrypt(b"x")


@pytest.mark.parametrize("bad", ["xyz", "ab" * 10, ""])
def test_chave_invalida(monkeypatch, bad):
    monkeypatch.setenv("CV_KEY", bad)
    monkeypatch.setattr(crypto, "KEY_FILE", "/nonexistent/cv.key")
    assert crypto.ready() is False
