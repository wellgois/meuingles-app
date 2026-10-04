"""Contas: senha (scrypt), sessões, tokens de e-mail, limite de tentativas, teste grátis e cotas."""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import Header, HTTPException

TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "7"))
TRIAL_AUDIO_MIN = int(os.environ.get("TRIAL_AUDIO_MIN", "120"))
MONTHLY_AUDIO_MIN = int(os.environ.get("MONTHLY_AUDIO_MIN", "300"))
LLM_PER_DAY = int(os.environ.get("LLM_PER_DAY", "40"))
SESSION_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- senha ----------

def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str | None) -> bool:
    try:
        _, salt, h = (stored or "").split("$")
        calc = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, TypeError):
        return False


def valid_email(e: str) -> bool:
    return bool(EMAIL_RE.match(e or "")) and len(e) <= 200


# ---------- tokens ----------

def new_token() -> tuple[str, str]:
    """Devolve (token para o cliente, hash para o banco)."""
    t = secrets.token_urlsafe(32)
    return t, hashlib.sha256(t.encode()).hexdigest()


def token_hash(t: str) -> str:
    return hashlib.sha256((t or "").encode()).hexdigest()


# ---------- limite de tentativas (memória do processo) ----------

_hits: dict[str, list[float]] = {}
_lock = threading.Lock()


def rate_limit(key: str, limit: int, window_s: int) -> None:
    now = time.time()
    with _lock:
        hits = [t for t in _hits.get(key, []) if now - t < window_s]
        if len(hits) >= limit:
            raise HTTPException(429, "Muitas tentativas. Espere alguns minutos e tente de novo.")
        hits.append(now)
        _hits[key] = hits


# ---------- sessão ----------

def make_current_user(db):
    def current_user(authorization: str = Header("")):
        tok = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        if not tok:
            raise HTTPException(401, "Entre na sua conta para continuar.")
        with db() as conn:
            user = conn.execute(
                """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.token_hash = %s AND s.expires_at > now()""", (token_hash(tok),)).fetchone()
        if not user:
            raise HTTPException(401, "Sua sessão expirou. Entre novamente.")
        return user
    return current_user


# ---------- acesso e cotas ----------

def access(user) -> dict:
    """Situação da conta para a interface e para as checagens."""
    now = datetime.now(timezone.utc)
    plan = user["plan"]
    ends = user.get("trial_ends_at")
    if plan == "trial" and ends is not None and ends <= now:
        plan = "expired"
    paid = user.get("paid_until")
    canceled = plan == "canceled"
    if plan in ("active", "canceled"):
        plan = "active" if paid is not None and paid > now else "expired"
    days_left = int(max(0, ((ends - now).total_seconds() + 86399) // 86400)) if ends and plan == "trial" else None
    return {"plan": plan, "trial_ends_at": ends.isoformat() if ends else None, "days_left": days_left,
            "email_verified": bool(user.get("email_verified")), "is_admin": bool(user.get("is_admin")),
            "paid_until": paid.isoformat() if paid else None, "canceled": canceled,
            "mp_status": user.get("mp_status")}


def audio_limit_ms(plan: str, tier: str | None = None) -> int | None:
    if plan == "owner":
        return None
    if plan == "active":
        from . import plans as _plans
        if tier in _plans.TIERS:
            return _plans.TIERS[tier]["audio_min"] * 60000
        return MONTHLY_AUDIO_MIN * 60000
    return TRIAL_AUDIO_MIN * 60000


def audio_used_ms(conn, user, plan: str) -> int:
    since = "date_trunc('month', now())" if plan == "active" else "'-infinity'::timestamptz"
    row = conn.execute(f"""SELECT coalesce(sum(audio_ms), 0) AS ms FROM attempts
                           WHERE user_id = %s AND engine = 'azure' AND created_at >= {since}""",
                       (user["id"],)).fetchone()
    return int(row["ms"])


def require_practice(user) -> str:
    """Barra gravações de quem não confirmou o e-mail ou está com o teste vencido. Devolve o plano."""
    a = access(user)
    if a["plan"] == "owner":
        return "owner"
    if not a["email_verified"]:
        raise HTTPException(403, "Confirme seu e-mail para começar a treinar. O link está na sua caixa de entrada.")
    if a["plan"] == "expired":
        raise HTTPException(402, "Seu acesso terminou. Escolha um plano na aba Assinatura para continuar treinando.")
    return a["plan"]


def llm_allowed(conn, user, plan: str) -> bool:
    if plan == "owner":
        return True
    row = conn.execute("""SELECT count(*) AS n FROM attempts WHERE user_id = %s AND used_llm
                          AND created_at > now() - interval '1 day'""", (user["id"],)).fetchone()
    return row["n"] < LLM_PER_DAY
