import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize("path", ["/api/admin/stats", "/api/admin/leads", "/api/admin/insights",
                                  "/api/admin/traffic", "/api/admin/costs"])
def test_admin_exige_login(path):
    assert client.get(path).status_code == 401


def test_track_ignora_ids_invalidos():
    assert client.post("/api/t", json={"pv": "x", "vid": "y", "sid": "z"}).status_code == 204


def test_track_ignora_bots():
    ids = {k: str(uuid.uuid4()) for k in ("pv", "vid", "sid")}
    r = client.post("/api/t", json=ids, headers={"user-agent": "Googlebot/2.1"})
    assert r.status_code == 204


def test_signup_valida_antes_de_tocar_no_banco():
    base = {"name": "Teste", "password": "senha-forte-123"}
    r = client.post("/api/auth/signup", json={**base, "email": "invalido", "accept_terms": True})
    assert r.status_code == 422
    r = client.post("/api/auth/signup", json={**base, "email": "a@b.co", "accept_terms": False})
    assert r.status_code == 422
