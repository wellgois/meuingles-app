"""Pseudonimização: HMAC-SHA256 com a chave só no servidor. Nada de e-mail ou nome sai do Postgres."""
import hashlib
import hmac
import os


def load_key() -> bytes:
    key = os.environ.get("PSEUDO_KEY", "")
    path = os.environ.get("PSEUDO_KEY_FILE")
    if not key and path:
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
    if len(key) < 32:
        raise RuntimeError("Chave de pseudonimização ausente ou curta (mínimo 32 caracteres).")
    return key.encode("utf-8")


def key_id(key: bytes) -> str:
    """Identificador curto da chave, para perceber no manifesto se ela foi trocada."""
    return hashlib.sha256(key).hexdigest()[:8]


def pseudo(key: bytes, value) -> str | None:
    if value is None:
        return None
    return hmac.new(key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()[:32]
