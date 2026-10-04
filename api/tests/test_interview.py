"""Simulador de entrevista: lógica pura e fluxo completo com banco e IA falsa. Só rodar contra um banco descartável."""
import json
import random
import uuid

import pytest
from fastapi.testclient import TestClient

from app import auth, interview
from app.main import app, db

client = TestClient(app)

GOOD = {"criteria": {"star": 80, "technical": 70, "vocabulary": 90, "grammar": 60, "clarity": 75},
        "strengths": ["a", "b", "c", "d"], "improvements": ["x", "y", "z", "w"],
        "weakest_question": 1, "natural_version": "Hello."}


# ---------- lógica pura ----------

def test_parse_report_valido():
    r = interview.parse_report("texto antes " + json.dumps(GOOD) + " depois")
    assert r["overall"] == 75
    assert r["criteria"] == GOOD["criteria"]
    assert len(r["strengths"]) == 3 and len(r["improvements"]) == 3
    assert r["weakest_question"] == 1


def test_parse_report_limita_notas_e_indice():
    d = dict(GOOD, criteria={**GOOD["criteria"], "star": 250, "grammar": -5}, weakest_question=9)
    r = interview.parse_report(json.dumps(d))
    assert r["criteria"]["star"] == 100 and r["criteria"]["grammar"] == 0
    assert r["weakest_question"] == 2


@pytest.mark.parametrize("text", ["", "sem json", "{}", '{"criteria": 5}', json.dumps({"criteria": {"star": 80}})])
def test_parse_report_invalido(text):
    assert interview.parse_report(text) is None


def test_parse_followup():
    assert interview.parse_followup('{"followup": "Why Delta?"}') == "Why Delta?"
    assert interview.parse_followup('{"followup": ""}') is None
    assert interview.parse_followup("nada") is None


def test_pick_questions_ordem_e_exclusao():
    qs = interview.pick_questions("especialista", set(), random.Random(1))
    assert [q["kind"] for q in qs] == ["behavioral", "technical", "design"]
    banned = set(interview.TECHNICAL[:-1])
    for seed in range(20):
        assert interview.pick_questions("pleno", banned, random.Random(seed))[1]["text"] == interview.TECHNICAL[-1]


def test_pick_questions_exclusao_total_nao_trava():
    q = interview.pick_questions(None, set(interview.TECHNICAL) | set(interview.DESIGN), random.Random(0))
    assert q[1]["text"] in interview.TECHNICAL


# ---------- fluxo com banco ----------

def make_user(plan="trial"):
    uid = uuid.uuid4()
    token, h = auth.new_token()
    with db() as conn:
        conn.execute("INSERT INTO users (id, name, email, plan, trial_ends_at, email_verified) "
                     "VALUES (%s, 'Teste', %s, %s, now() + interval '7 days', true)", (uid, f"{uid}@example.test", plan))
        conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + interval '1 day')",
                     (h, uid))
    return uid, {"Authorization": f"Bearer {token}"}


def drop_user(uid):
    with db() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (uid,))


def start(h):
    return client.post("/api/interview/start", headers=h)


def answer(h, sid, text="I led a migration and cut costs by 30 percent."):
    return client.post(f"/api/interview/{sid}/answer", json={"answer": text, "duration_ms": 30000}, headers=h)


@pytest.fixture()
def fake_llm(monkeypatch):
    calls = []

    def chat(system, user_text, max_tokens=700, model=None):
        calls.append(system)
        if system == interview.FOLLOWUP_SYSTEM:
            return json.dumps({"followup": "Can you give a concrete number?"}), {"in": 100, "out": 20}
        return json.dumps(GOOD), {"in": 500, "out": 300}

    monkeypatch.setattr(interview.llm, "chat", chat)
    monkeypatch.setattr(interview.llm, "configured", lambda: True)
    monkeypatch.setattr(interview, "FOLLOWUPS", True)
    return calls


def test_exige_login():
    assert client.get("/api/interview/state").status_code == 401
    assert client.post("/api/interview/start").status_code == 401


def test_fluxo_completo(fake_llm):
    uid, h = make_user()
    try:
        r = start(h)
        assert r.status_code == 200
        active = r.json()["active"]
        sid = active["session_id"]
        assert active["prompt"]["kind"] == "question" and active["prompt"]["q_index"] == 0
        steps = []
        for _ in range(6):
            r = answer(h, sid)
            assert r.status_code == 200, r.text
            out = r.json()
            if out.get("ready"):
                break
            steps.append((out["q_index"], out["kind"]))
        assert out.get("ready") is True
        assert steps == [(0, "followup"), (1, "question"), (1, "followup"), (2, "question"), (2, "followup")]

        r = client.post(f"/api/interview/{sid}/finish", headers=h)
        assert r.status_code == 200, r.text
        rep = r.json()
        assert rep["overall"] == 75 and rep["passed"] is True
        assert rep["passes"] == 1 and rep["passes_needed"] == 2 and rep["level_complete"] is False
        assert len(rep["questions"]) == 3

        with db() as conn:
            s = conn.execute("SELECT status, overall, llm_in_tokens, llm_out_tokens FROM interview_sessions "
                             "WHERE id = %s", (sid,)).fetchone()
        assert s["status"] == "finished" and float(s["overall"]) == 75.0
        assert (s["llm_in_tokens"], s["llm_out_tokens"]) == (800, 360)

        calls = len(fake_llm)
        again = client.post(f"/api/interview/{sid}/finish", headers=h)
        assert again.status_code == 200 and len(fake_llm) == calls

        st = client.get("/api/interview/state", headers=h).json()
        assert st["active"] is None and st["passes"] == 1 and len(st["history"]) == 1
        assert client.get(f"/api/interview/{sid}/report", headers=h).json()["overall"] == 75
    finally:
        drop_user(uid)


def test_start_retoma_a_sessao_ativa(fake_llm):
    uid, h = make_user()
    try:
        a = start(h).json()["active"]["session_id"]
        b = start(h).json()["active"]["session_id"]
        assert a == b
    finally:
        drop_user(uid)


def test_limite_diario_e_dono_isento(fake_llm, monkeypatch):
    monkeypatch.setattr(interview, "PER_DAY", 1)
    uid, h = make_user()
    owner, ho = make_user(plan="owner")
    try:
        sid = start(h).json()["active"]["session_id"]
        assert client.post(f"/api/interview/{sid}/abandon", headers=h).status_code == 200
        assert start(h).status_code == 429
        for _ in range(2):
            osid = start(ho).json()["active"]["session_id"]
            assert client.post(f"/api/interview/{osid}/abandon", headers=ho).status_code == 200
    finally:
        drop_user(uid)
        drop_user(owner)


def test_sessao_de_outro_usuario_nao_e_acessivel(fake_llm):
    u1, h1 = make_user()
    u2, h2 = make_user()
    try:
        sid = start(h1).json()["active"]["session_id"]
        assert answer(h2, sid).status_code == 404
        assert client.post(f"/api/interview/{sid}/finish", headers=h2).status_code == 404
        assert client.post(f"/api/interview/{sid}/abandon", headers=h2).status_code == 404
        assert client.get(f"/api/interview/{sid}/report", headers=h2).status_code == 404
    finally:
        drop_user(u1)
        drop_user(u2)


def test_validacoes(fake_llm):
    uid, h = make_user()
    try:
        sid = start(h).json()["active"]["session_id"]
        assert answer(h, sid, "  ").status_code == 422
        assert client.post(f"/api/interview/{sid}/finish", headers=h).status_code == 409
        assert client.post("/api/interview/nao-e-uuid/answer", json={"answer": "abc def"}, headers=h).status_code == 404
    finally:
        drop_user(uid)


def test_sem_ia_pula_followups_e_finalizar_pode_repetir(monkeypatch):
    monkeypatch.setattr(interview.llm, "configured", lambda: True)
    monkeypatch.setattr(interview, "FOLLOWUPS", True)
    monkeypatch.setattr(interview.llm, "chat", lambda *a, **k: None)
    uid, h = make_user()
    try:
        sid = start(h).json()["active"]["session_id"]
        outs = [answer(h, sid).json() for _ in range(3)]
        assert [o.get("q_index") for o in outs[:2]] == [1, 2]
        assert outs[2].get("ready") is True
        assert client.post(f"/api/interview/{sid}/finish", headers=h).status_code == 502
        monkeypatch.setattr(interview.llm, "chat", lambda *a, **k: (json.dumps(GOOD), {"in": 10, "out": 5}))
        assert client.post(f"/api/interview/{sid}/finish", headers=h).status_code == 200
    finally:
        drop_user(uid)


def test_exclusao_da_conta_apaga_as_sessoes(fake_llm):
    uid, h = make_user()
    sid = start(h).json()["active"]["session_id"]
    drop_user(uid)
    with db() as conn:
        assert conn.execute("SELECT count(*) AS n FROM interview_sessions WHERE id = %s", (sid,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM interview_turns WHERE session_id = %s", (sid,)).fetchone()["n"] == 0


def test_abandonar_descarta_as_respostas_e_conta_no_limite(fake_llm):
    uid, h = make_user()
    try:
        sid = start(h).json()["active"]["session_id"]
        assert answer(h, sid).status_code == 200
        assert client.post(f"/api/interview/{sid}/abandon", headers=h).status_code == 200
        with db() as conn:
            assert conn.execute("SELECT count(*) AS n FROM interview_turns WHERE session_id = %s", (sid,)).fetchone()["n"] == 0
            assert conn.execute("SELECT status FROM interview_sessions WHERE id = %s", (sid,)).fetchone()["status"] == "abandoned"
            assert interview.used_today(conn, uid) == 1
    finally:
        drop_user(uid)


def test_relatorio_pronto_apaga_o_texto_das_respostas(fake_llm):
    uid, h = make_user()
    try:
        sid = start(h).json()["active"]["session_id"]
        for _ in range(6):
            if answer(h, sid, "my secret answer text").json().get("ready"):
                break
        assert client.post(f"/api/interview/{sid}/finish", headers=h).status_code == 200
        with db() as conn:
            assert conn.execute("SELECT count(*) AS n FROM interview_turns WHERE session_id = %s", (sid,)).fetchone()["n"] == 0
            rep = conn.execute("SELECT report FROM interview_sessions WHERE id = %s", (sid,)).fetchone()["report"]
        assert "secret answer" not in json.dumps(rep)
        assert client.get(f"/api/interview/{sid}/report", headers=h).status_code == 200
    finally:
        drop_user(uid)
