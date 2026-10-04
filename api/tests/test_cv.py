"""Currículo: leitura, remoção de contato, perfil, criptografia em repouso, isolamento e exclusão (banco descartável)."""
import html
import io
import json
import uuid
import zipfile
from urllib.parse import quote

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth, crypto, cv
from app.main import app, db

client = TestClient(app)

PROFILE = {"headline": "Data Engineer", "summary": "Builds data pipelines.", "years_experience": 5,
           "skills": ["Python", "SQL", "Airflow"],
           "experience": [{"title": "Data Engineer", "company": "Acme", "period": "2019-2024",
                           "highlights": ["Cut platform cost by 30%"]}],
           "projects": [{"name": "Lakehouse", "description": "Built bronze, silver and gold layers.",
                         "stack": ["Delta Lake"], "result": "Used by 12 business areas"}],
           "education": ["BSc in Mathematics"], "certifications": [], "languages": ["Portuguese", "English"],
           "source_language": "pt"}

CV_LINES = [
    "Wellington Silva",
    "Email: pessoa@example.com | Tel: (21) 98765-4321",
    "CPF: 123.456.789-09",
    "Data de nascimento: 01/02/1990",
    "Engenheiro de dados com 5 anos de experiência em Python, SQL e Airflow.",
    "Experiência: Acme Ltda, 2019-2024, reduziu o custo da plataforma de dados em 30% migrando os jobs para Delta Lake.",
    "Projeto: lakehouse com camadas bronze, prata e ouro, usado por 12 áreas de negócio.",
    "Formação: Licenciatura em Matemática. Certificações: Databricks Data Engineer Associate.",
    "https://www.linkedin.com/in/pessoa",
]


def make_docx(lines):
    body = "".join(f"<w:p><w:r><w:t>{html.escape(line)}</w:t></w:r></w:p>" for line in lines)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           'wordprocessingml/2006/main"><w:body>' + body + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def make_pdf(lines):
    content = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objs = ["<</Type/Catalog/Pages 2 0 R>>",
            "<</Type/Pages/Kids[3 0 R]/Count 1>>",
            "<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
            f"<</Length {len(content)}>>\nstream\n{content}\nendstream",
            "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


# ---------- lógica pura ----------

def test_redact_remove_contato_e_preserva_datas():
    text = ("Contato: pessoa@example.com (21) 98765-4321 +55 21 98765-4321 21 98765-4321 123.456.789-09 20000-123 "
            "https://x.com/a www.site.com\nExperiência 2019-2022 e Jan 2020 - Mar 2023\n"
            "Endereço: Rua A, 10\nNascimento: 01/02/1990")
    out = cv.redact(text)
    for secret in ("pessoa@example", "98765", "123.456", "20000-123", "x.com", "site.com", "Rua A", "01/02/1990"):
        assert secret not in out
    assert "2019-2022" in out and "Jan 2020 - Mar 2023" in out


def test_detecta_tipos():
    assert cv.detect_kind(make_pdf(["abc"])) == "pdf"
    assert cv.detect_kind(make_docx(["abc"])) == "docx"
    assert cv.detect_kind(b"texto qualquer") is None


def test_extrai_texto_de_docx_e_pdf():
    assert "Python" in cv.extract_docx(make_docx(["Experiencia com Python & SQL"]))
    assert "Python" in cv.extract_pdf(make_pdf(["Experiencia com Python e SQL"])).replace("\n", " ")


def test_docx_com_doctype_e_recusado():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]>'
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
    with pytest.raises(HTTPException) as e:
        cv.extract_docx(buf.getvalue())
    assert e.value.status_code == 422


def test_validate_profile_limita_e_ignora_extras():
    p = cv.validate_profile({"headline": "x" * 500, "skills": ["a"] * 100, "unknown": 1, "years_experience": 99,
                             "experience": [{"title": "T", "company": "C", "highlights": ["h"] * 20}] * 20,
                             "source_language": "xx"})
    assert len(p["headline"]) == 120 and len(p["skills"]) == 40
    assert len(p["experience"]) == 8 and len(p["experience"][0]["highlights"]) == 6
    assert p["years_experience"] is None and p["source_language"] == "other" and "unknown" not in p
    assert cv.validate_profile({}) is None and cv.validate_profile("x") is None


# ---------- fluxo com banco ----------

def make_user():
    uid = uuid.uuid4()
    token, h = auth.new_token()
    with db() as conn:
        conn.execute("INSERT INTO users (id, name, email, plan, trial_ends_at, email_verified) "
                     "VALUES (%s, 'Teste', %s, 'trial', now() + interval '7 days', true)", (uid, f"{uid}@example.test"))
        conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + interval '1 day')",
                     (h, uid))
    return uid, {"Authorization": f"Bearer {token}"}


def drop_user(uid):
    with db() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (uid,))


def upload(h, data, name="", **params):
    headers = dict(h)
    if name:
        headers["X-File-Name"] = quote(name)
    return client.post("/api/cv", params=params, content=data, headers=headers)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CV_KEY", "ab" * 32)
    sent = []

    def chat(system, user_text, max_tokens=700, model=None, temperature=None):
        sent.append(user_text)
        return "Aqui está: " + json.dumps(PROFILE), {"in": 700, "out": 300}

    monkeypatch.setattr(cv.llm, "chat", chat)
    monkeypatch.setattr(cv.llm, "configured", lambda: True)
    return {"sent": sent}


def test_exige_login():
    assert client.get("/api/cv").status_code == 401
    assert client.post("/api/cv").status_code == 401
    assert client.get("/api/cv/file").status_code == 401


def test_fluxo_completo_docx(env):
    uid, h = make_user()
    try:
        assert client.get("/api/cv", headers=h).json()["consent"]["accepted"] is False
        assert upload(h, make_docx(CV_LINES), kind="file").status_code == 403
        assert client.post("/api/cv/consent", headers=h).json()["consent"]["accepted"] is True

        docx = make_docx(CV_LINES)
        r = upload(h, docx, kind="file", name="meu cv.docx")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["has_cv"] and body["file_kind"] == "docx" and body["file_name"] == "meu cv.docx"
        assert body["profile"]["headline"] == "Data Engineer"

        sent = env["sent"][-1]
        for secret in ("pessoa@example", "98765", "123.456", "linkedin", "01/02/1990"):
            assert secret not in sent
        assert "Delta Lake" in sent

        with db() as conn:
            row = conn.execute("SELECT profile_enc, file_name_enc, llm_in_tokens, llm_out_tokens FROM cv_documents "
                               "WHERE user_id = %s", (uid,)).fetchone()
        raw = bytes(row["profile_enc"]) + bytes(row["file_name_enc"])
        assert b"Data Engineer" not in raw and b"meu cv" not in raw
        assert (row["llm_in_tokens"], row["llm_out_tokens"]) == (700, 300)

        d = client.get("/api/cv/file", headers=h)
        assert d.status_code == 200 and d.content == docx
        assert d.headers["x-content-type-options"] == "nosniff"

        edited = dict(body["profile"], headline="Senior Data Engineer")
        assert client.put("/api/cv/profile", json=edited, headers=h).json()["profile"]["headline"] == "Senior Data Engineer"
        assert client.put("/api/cv/profile", json={}, headers=h).status_code == 422

        assert client.delete("/api/cv", headers=h).json()["has_cv"] is False
        assert client.get("/api/cv/file", headers=h).status_code == 404
        assert client.get("/api/cv", headers=h).json()["consent"]["accepted"] is True
        assert client.delete("/api/cv/consent", headers=h).json()["consent"]["accepted"] is False
    finally:
        drop_user(uid)


def test_texto_colado_fica_criptografado(env):
    uid, h = make_user()
    try:
        client.post("/api/cv/consent", headers=h)
        text = "\n".join(CV_LINES).encode("utf-8")
        assert upload(h, text, kind="text").status_code == 200
        with db() as conn:
            row = conn.execute("SELECT file_enc FROM cv_documents WHERE user_id = %s", (uid,)).fetchone()
        assert b"Delta Lake" not in bytes(row["file_enc"])
        d = client.get("/api/cv/file", headers=h)
        assert d.content == text and d.headers["content-type"].startswith("text/plain")
    finally:
        drop_user(uid)


def test_usuario_nao_ve_o_curriculo_de_outro(env):
    u1, h1 = make_user()
    u2, h2 = make_user()
    try:
        client.post("/api/cv/consent", headers=h1)
        assert upload(h1, make_docx(CV_LINES), kind="file").status_code == 200
        assert client.get("/api/cv/file", headers=h2).status_code == 404
        assert client.get("/api/cv", headers=h2).json()["has_cv"] is False
        assert client.put("/api/cv/profile", json=PROFILE, headers=h2).status_code == 404
    finally:
        drop_user(u1)
        drop_user(u2)


def test_validacoes_e_falhas(env, monkeypatch):
    uid, h = make_user()
    try:
        client.post("/api/cv/consent", headers=h)
        assert upload(h, b"nao sou pdf nem docx", kind="file").status_code == 422
        assert upload(h, b"curto demais", kind="text").status_code == 422
        assert upload(h, b"x" * (cv.MAX_FILE + 1), kind="file").status_code == 413
        monkeypatch.setattr(cv.llm, "chat", lambda *a, **k: None)
        assert upload(h, make_docx(CV_LINES), kind="file").status_code == 502
        monkeypatch.delenv("CV_KEY")
        monkeypatch.setattr(crypto, "KEY_FILE", "/nonexistent/cv.key")
        assert upload(h, make_docx(CV_LINES), kind="file").status_code == 503
    finally:
        drop_user(uid)


def test_consentimento_de_versao_antiga_nao_vale(env):
    uid, h = make_user()
    try:
        client.post("/api/cv/consent", headers=h)
        with db() as conn:
            conn.execute("UPDATE user_consents SET version = '2000-01-01' WHERE user_id = %s", (uid,))
        assert upload(h, make_docx(CV_LINES), kind="file").status_code == 403
    finally:
        drop_user(uid)


def test_exclusao_da_conta_apaga_curriculo_e_consentimentos(env):
    uid, h = make_user()
    client.post("/api/cv/consent", headers=h)
    assert upload(h, make_docx(CV_LINES), kind="file").status_code == 200
    drop_user(uid)
    with db() as conn:
        assert conn.execute("SELECT count(*) AS n FROM cv_documents WHERE user_id = %s", (uid,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM user_consents WHERE user_id = %s", (uid,)).fetchone()["n"] == 0


def test_resposta_truncada_da_ia_vira_aviso_claro(env, monkeypatch):
    uid, h = make_user()
    try:
        client.post("/api/cv/consent", headers=h)
        monkeypatch.setattr(cv.llm, "chat", lambda *a, **k: ('{"headline": "x', {"in": 10, "out": 3500, "stop": "max_tokens"}))
        r = upload(h, make_docx(CV_LINES), kind="file")
        assert r.status_code == 422 and "extenso" in r.json()["detail"]
    finally:
        drop_user(uid)


def test_nome_do_arquivo_so_pelo_cabecalho(env):
    uid, h = make_user()
    try:
        client.post("/api/cv/consent", headers=h)
        r = client.post("/api/cv", params={"kind": "file", "name": "da-url.docx"}, content=make_docx(CV_LINES), headers=h)
        assert r.status_code == 200 and "file_name" not in r.json()
    finally:
        drop_user(uid)
