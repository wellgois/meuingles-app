import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import auth


def now():
    return datetime.now(timezone.utc)


def user(**kw):
    base = {"plan": "trial", "trial_ends_at": now() + timedelta(days=3), "paid_until": None,
            "email_verified": True, "is_admin": False, "mp_status": None}
    base.update(kw)
    return base


def test_password_roundtrip():
    h = auth.hash_password("senha-forte-123")
    assert h.startswith("scrypt$")
    assert auth.check_password("senha-forte-123", h)
    assert not auth.check_password("outra-senha", h)


@pytest.mark.parametrize("stored", [None, "", "lixo", "a$b"])
def test_password_hash_invalido(stored):
    assert not auth.check_password("x", stored)


@pytest.mark.parametrize("email,ok", [
    ("a@b.co", True), ("nome.sobrenome@empresa.com.br", True), ("sem-arroba", False),
    ("a@b", False), ("", False), ("a b@c.com", False), ("a@" + "x" * 200 + ".com", False)])
def test_valid_email(email, ok):
    assert auth.valid_email(email) is ok


def test_tokens():
    t, h = auth.new_token()
    assert h == auth.token_hash(t)
    assert len(t) > 30
    assert t != auth.new_token()[0]


def test_access_trial_ativo():
    a = auth.access(user())
    assert a["plan"] == "trial"
    assert a["days_left"] in (2, 3)


def test_access_trial_vencido():
    a = auth.access(user(trial_ends_at=now() - timedelta(minutes=1)))
    assert a["plan"] == "expired"
    assert a["days_left"] is None


def test_access_assinante_vigente():
    a = auth.access(user(plan="active", paid_until=now() + timedelta(days=10)))
    assert a["plan"] == "active"
    assert a["canceled"] is False


def test_access_assinatura_vencida_ou_sem_data():
    assert auth.access(user(plan="active", paid_until=now() - timedelta(days=1)))["plan"] == "expired"
    assert auth.access(user(plan="active", paid_until=None))["plan"] == "expired"


def test_access_cancelada_com_prazo():
    a = auth.access(user(plan="canceled", paid_until=now() + timedelta(days=5)))
    assert a["plan"] == "active"
    assert a["canceled"] is True


def test_access_dono():
    assert auth.access(user(plan="owner"))["plan"] == "owner"


def test_limites_de_audio():
    assert auth.audio_limit_ms("owner") is None
    assert auth.audio_limit_ms("active") == auth.MONTHLY_AUDIO_MIN * 60000
    assert auth.audio_limit_ms("trial") == auth.TRIAL_AUDIO_MIN * 60000
    assert auth.audio_limit_ms("expired") == auth.TRIAL_AUDIO_MIN * 60000


def test_require_practice():
    assert auth.require_practice(user()) == "trial"
    assert auth.require_practice(user(plan="owner")) == "owner"
    with pytest.raises(HTTPException) as e:
        auth.require_practice(user(email_verified=False))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        auth.require_practice(user(trial_ends_at=now() - timedelta(days=1)))
    assert e.value.status_code == 402


def test_rate_limit():
    key = "teste:" + uuid.uuid4().hex
    auth.rate_limit(key, 2, 60)
    auth.rate_limit(key, 2, 60)
    with pytest.raises(HTTPException) as e:
        auth.rate_limit(key, 2, 60)
    assert e.value.status_code == 429
