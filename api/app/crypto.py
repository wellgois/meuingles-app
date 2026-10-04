"""Criptografia em repouso para dados pessoais (currículos): AES-256-GCM, chave em arquivo fora do banco e dos backups."""
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = b"\x01"
KEY_FILE = os.environ.get("CV_KEY_FILE", "/run/secrets/cv.key")


class CryptoError(RuntimeError):
    pass


def _load_key() -> bytes:
    raw = os.environ.get("CV_KEY", "").strip()
    if not raw:
        try:
            with open(KEY_FILE, encoding="utf-8") as f:
                raw = f.read().strip()
        except OSError:
            raise CryptoError("chave de criptografia ausente")
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        raise CryptoError("chave inválida: use 64 caracteres hexadecimais")
    if len(key) != 32:
        raise CryptoError("chave inválida: use 64 caracteres hexadecimais")
    return key


def ready() -> bool:
    try:
        _load_key()
        return True
    except CryptoError:
        return False


def encrypt(plaintext: bytes, aad: bytes = b"") -> bytes:
    key = _load_key()
    nonce = secrets.token_bytes(12)
    return VERSION + nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(blob: bytes, aad: bytes = b"") -> bytes:
    blob = bytes(blob)
    if len(blob) < 1 + 12 + 16 or blob[:1] != VERSION:
        raise CryptoError("dado criptografado inválido")
    try:
        return AESGCM(_load_key()).decrypt(blob[1:13], blob[13:], aad)
    except InvalidTag:
        raise CryptoError("falha de integridade ao decifrar")


if __name__ == "__main__":
    probe = b"selftest"
    ok = decrypt(encrypt(probe, b"x"), b"x") == probe
    print("criptografia ok" if ok else "criptografia FALHOU")
    raise SystemExit(0 if ok else 1)
