import json
import os
import time
import uuid
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from . import auth, azure_speech, billing, content, jobs, leads, llm, mailer, traffic, costs, interview, cv, plans
from .scoring import SHORT, score_open, score_repeat

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost/meuingles")
WEB_DIR = Path(os.environ.get("WEB_DIR", Path(__file__).resolve().parents[2] / "web"))
TZ = "America/Sao_Paulo"
INTERVALS = [1, 3, 7, 14, 30]
MAX_LEVEL_BASIC = 4

app = FastAPI(title="MeuInglês API", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def fresh_pages(request: Request, call_next):
    """Faz o navegador conferir a versão das páginas a cada visita (responde 304 se nada mudou)."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def db():
    return psycopg.connect(DB_URL, row_factory=dict_row, autocommit=True)


@app.on_event("startup")
def init_schema():
    sql = (Path(__file__).parent / "schema.sql").read_text()
    for attempt in range(30):
        try:
            with db() as conn:
                conn.execute(sql)
            jobs.start(db)
            return
        except psycopg.OperationalError:
            time.sleep(2)
    raise RuntimeError("Banco de dados indisponível depois de 60 s")


current_user = auth.make_current_user(db)
leads.register(app, db, current_user)
traffic.register(app, db, current_user)
costs.register(app, db, current_user)
interview.register(app, db, current_user)
cv.register(app, db, current_user)


# ---------- públicos ----------

@app.get("/api/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "engine": "azure" if azure_speech.configured() else "browser",
            "azure_configured": azure_speech.configured(), "llm_configured": llm.configured(),
            "contact": os.environ.get("CONTACT_EMAIL", "")}


# ---------- contas ----------

class SignUp(BaseModel):
    promo: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)
    accept_terms: bool
    track: str | None = None
    vid: str | None = Field(default=None, max_length=40)
    utm_source: str = Field(default="", max_length=80)
    utm_campaign: str = Field(default="", max_length=80)
    utm_content: str = Field(default="", max_length=80)
    ref: str = Field(default="", max_length=120)
    inapp: str = Field(default="", max_length=20)


class Login(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class Forgot(BaseModel):
    email: str = Field(max_length=200)


class Reset(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)


class Confirm(BaseModel):
    password: str = Field(max_length=200)


def open_session(conn, user_id) -> str:
    tok, h = auth.new_token()
    conn.execute(f"INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + interval '{auth.SESSION_DAYS} days')",
                 (h, user_id))
    return tok


def send_verify(conn, user) -> bool:
    tok, h = auth.new_token()
    conn.execute("INSERT INTO email_tokens (token_hash, user_id, kind, expires_at) VALUES (%s, %s, 'verify', now() + interval '1 day')",
                 (h, user["id"]))
    return mailer.send(user["email"], "Confirme seu e-mail no MeuInglês", [
        f"Oi, {user['name'].split(' ')[0]}! Falta só confirmar seu e-mail para começar o teste grátis de {auth.access(user)['days_left'] or auth.TRIAL_DAYS} dias.",
        "O link vale por 24 horas."], ("Confirmar e-mail", mailer.base_url() + "api/auth/verify?token=" + tok))


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@app.post("/api/auth/signup")
def signup(body: SignUp, request: Request):
    promo = (body.promo or "").strip().lower()
    auth.rate_limit(("signup-promo:" if promo else "signup:") + client_ip(request), 40 if promo else 5, 3600)
    email = body.email.strip().lower()
    if not auth.valid_email(email):
        raise HTTPException(422, "Digite um e-mail válido.")
    if not body.accept_terms:
        raise HTTPException(422, "Para criar a conta, aceite os termos de uso e a política de privacidade.")
    track = body.track if body.track in content.TRACKS else None
    with db() as conn:
        with conn.transaction():
            if conn.execute("SELECT 1 FROM users WHERE lower(email) = %s", (email,)).fetchone():
                raise HTTPException(409, "Já existe uma conta com esse e-mail. Entre ou use 'Esqueci minha senha'.")
            promo_row = None
            if promo:
                promo_row = conn.execute(
                    "UPDATE promo_codes SET used_count = used_count + 1 WHERE code = %s AND active "
                    "AND (expires_at IS NULL OR expires_at > now()) AND (max_uses IS NULL OR used_count < max_uses) "
                    "RETURNING code, trial_days", (promo,)).fetchone()
                if not promo_row:
                    raise HTTPException(422, "Código promocional inválido, expirado ou esgotado.")
            trial_days = int(promo_row["trial_days"]) if promo_row else auth.TRIAL_DAYS
            uid = uuid.uuid4()
            user = conn.execute(
                f"""INSERT INTO users (id, name, email, pass_hash, plan, trial_ends_at, terms_accepted_at, target_level)
                    VALUES (%s, %s, %s, %s, 'trial', now() + interval '{trial_days} days', now(), %s) RETURNING *""",
                (uid, body.name.strip(), email, auth.hash_password(body.password), track)).fetchone()
            s_src, s_camp, s_cont, s_vid = traffic.signup_attribution(body)
            conn.execute("UPDATE users SET signup_source = %s, signup_campaign = %s, signup_content = %s, signup_vid = %s WHERE id = %s",
                         (s_src, s_camp, s_cont, s_vid, uid))
            if promo_row:
                conn.execute("UPDATE users SET promo_code = %s WHERE id = %s", (promo_row["code"], uid))
            tok = open_session(conn, uid)
        sent = send_verify(conn, user)
    return {"token": tok, "email_sent": sent}


@app.post("/api/auth/login")
def login(body: Login, request: Request):
    email = body.email.strip().lower()
    auth.rate_limit("login:" + client_ip(request) + ":" + email, 10, 900)
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE lower(email) = %s", (email,)).fetchone()
        if not user or not auth.check_password(body.password, user["pass_hash"]):
            raise HTTPException(401, "E-mail ou senha incorretos.")
        return {"token": open_session(conn, user["id"])}


@app.post("/api/auth/logout")
def logout(request: Request):
    h = request.headers.get("authorization", "")
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (auth.token_hash(h[7:]),))
    return {"ok": True}


@app.get("/api/auth/verify")
def verify(token: str = ""):
    with db() as conn:
        row = conn.execute("""UPDATE email_tokens SET used_at = now() WHERE token_hash = %s AND kind = 'verify'
                              AND used_at IS NULL AND expires_at > now() RETURNING user_id""",
                           (auth.token_hash(token),)).fetchone()
        if row:
            conn.execute("UPDATE users SET email_verified = true WHERE id = %s", (row["user_id"],))
    return RedirectResponse(mailer.base_url() + ("app/?verified=1" if row else "app/?verified=0"))


@app.post("/api/auth/resend")
def resend(request: Request, user=Depends(current_user)):
    auth.rate_limit("resend:" + str(user["id"]), 3, 3600)
    if user["email_verified"]:
        return {"sent": False, "already": True}
    with db() as conn:
        return {"sent": send_verify(conn, user)}


@app.post("/api/auth/forgot")
def forgot(body: Forgot, request: Request):
    auth.rate_limit("forgot:" + client_ip(request), 5, 3600)
    email = body.email.strip().lower()
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE lower(email) = %s", (email,)).fetchone()
        if user:
            tok, h = auth.new_token()
            conn.execute("INSERT INTO email_tokens (token_hash, user_id, kind, expires_at) VALUES (%s, %s, 'reset', now() + interval '1 hour')",
                         (h, user["id"]))
            mailer.send(user["email"], "Crie uma nova senha no MeuInglês", [
                "Recebemos um pedido para trocar a senha da sua conta. O link vale por 1 hora.",
                "Se não foi você, ignore este e-mail: sua senha continua a mesma."],
                ("Criar nova senha", mailer.base_url() + "app/?reset=" + tok))
    return {"ok": True}


@app.post("/api/auth/reset")
def reset(body: Reset):
    with db() as conn:
        with conn.transaction():
            row = conn.execute("""UPDATE email_tokens SET used_at = now() WHERE token_hash = %s AND kind = 'reset'
                                  AND used_at IS NULL AND expires_at > now() RETURNING user_id""",
                               (auth.token_hash(body.token),)).fetchone()
            if not row:
                raise HTTPException(400, "Link vencido ou já usado. Peça um novo em 'Esqueci minha senha'.")
            conn.execute("UPDATE users SET pass_hash = %s, email_verified = true WHERE id = %s",
                         (auth.hash_password(body.password), row["user_id"]))
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (row["user_id"],))
            return {"token": open_session(conn, row["user_id"])}


def account_info(conn, user) -> dict:
    a = auth.access(user)
    limit = auth.audio_limit_ms(a["plan"], user.get("tier"))
    used = auth.audio_used_ms(conn, user, a["plan"])
    a.update({"name": user["name"], "email": user["email"], "wants_subscription": user["wants_subscription_at"] is not None,
              "track": user.get("target_level"), "tracks": content.TRACKS,
              "billing": billing.configured(), "price": billing.PRICE, "mp_payer_email": user.get("mp_payer_email"),
              "audio_used_min": round(used / 60000), "audio_limit_min": None if limit is None else round(limit / 60000)})
    sims_used = conn.execute("SELECT count(*) AS n FROM interview_sessions WHERE user_id = %s "
                             "AND created_at >= date_trunc('month', now())", (user["id"],)).fetchone()["n"]
    t = plans.TIERS.get(user.get("tier"))
    a.update({"tier": user.get("tier"), "tiers": plans.public(), "sims_used": sims_used,
              "sims_limit": t["sims"] if t and a["plan"] == "active" else None})
    return a


@app.get("/api/me")
def me(user=Depends(current_user)):
    with db() as conn:
        return account_info(conn, user)


@app.post("/api/me/interest")
def interest(user=Depends(current_user)):
    with db() as conn:
        conn.execute("UPDATE users SET wants_subscription_at = coalesce(wants_subscription_at, now()) WHERE id = %s", (user["id"],))
    return {"ok": True}


class TrackIn(BaseModel):
    track: str


@app.post("/api/me/track")
def set_track(body: TrackIn, user=Depends(current_user)):
    if body.track not in content.TRACKS:
        raise HTTPException(422, "Escolha uma das trilhas.")
    with db() as conn:
        conn.execute("UPDATE users SET target_level = %s WHERE id = %s", (body.track, user["id"]))
    return {"ok": True, "track": body.track}


# ---------- assinatura (Mercado Pago) ----------

class SubscribeIn(BaseModel):
    payer_email: str = Field(max_length=200)
    tier: str | None = Field(default=None, max_length=20)


class SyncIn(BaseModel):
    preapproval_id: str | None = Field(default=None, max_length=100)


def _mp_error(e: Exception):
    raise HTTPException(502, "O Mercado Pago não respondeu como esperado. Tente de novo em alguns minutos.") from e


@app.post("/api/billing/subscribe")
def subscribe(body: SubscribeIn, user=Depends(current_user)):
    auth.rate_limit("subscribe:" + str(user["id"]), 6, 3600)
    if body.tier not in plans.TIERS:
        raise HTTPException(422, "Escolha um plano.")
    if not billing.configured():
        raise HTTPException(503, "A assinatura ainda não está disponível.")
    if user["plan"] == "owner":
        raise HTTPException(400, "A conta do dono não precisa de assinatura.")
    if not user["email_verified"]:
        raise HTTPException(403, "Confirme seu e-mail antes de assinar.")
    if auth.access(user)["plan"] == "active" and user.get("mp_status") == "authorized":
        raise HTTPException(400, "Sua assinatura já está ativa.")
    payer = body.payer_email.strip().lower()
    if not auth.valid_email(payer):
        raise HTTPException(422, "Digite o e-mail da sua conta do Mercado Pago.")
    try:
        pre = billing.create(user, payer, body.tier)
    except Exception as e:  # noqa: BLE001
        _mp_error(e)
    with db() as conn:
        conn.execute("""UPDATE users SET mp_preapproval_id = %s, mp_status = %s, mp_payer_email = %s, pending_tier = %s, mp_created_at = now()
                        WHERE id = %s""", (pre["id"], pre.get("status", "pending"), payer, body.tier, user["id"]))
    return {"url": pre["init_point"]}


@app.post("/api/billing/sync")
def billing_sync(body: SyncIn, user=Depends(current_user)):
    auth.rate_limit("sync:" + str(user["id"]), 20, 3600)
    pid = body.preapproval_id or user.get("mp_preapproval_id")
    if not pid or not billing.configured():
        return {"status": None}
    try:
        pre = billing.get(pid)
    except Exception as e:  # noqa: BLE001
        _mp_error(e)
    if pre.get("external_reference") != str(user["id"]):
        raise HTTPException(403, "Essa assinatura não é desta conta.")
    with db() as conn:
        billing.apply(conn, pre)
    return {"status": pre.get("status")}


@app.post("/api/billing/cancel")
def billing_cancel(user=Depends(current_user)):
    pid = user.get("mp_preapproval_id")
    if not pid or user.get("mp_status") != "authorized":
        raise HTTPException(400, "Não há assinatura ativa para cancelar.")
    try:
        pre = billing.cancel(pid)
        if pre.get("status") != "cancelled":
            pre = billing.get(pid)
    except Exception as e:  # noqa: BLE001
        _mp_error(e)
    with db() as conn:
        billing.apply(conn, pre)
    return {"status": pre.get("status")}


class PixIn(BaseModel):
    tier: str | None = Field(default=None, max_length=20)


class PixCheckIn(BaseModel):
    payment_id: str = Field(max_length=40)


@app.post("/api/billing/pix")
def pix_create(body: PixIn | None = None, user=Depends(current_user)):
    auth.rate_limit("pix:" + str(user["id"]), 10, 3600)
    tier = body.tier if body else None
    if tier not in plans.TIERS:
        raise HTTPException(422, "Escolha um plano.")
    if not billing.configured():
        raise HTTPException(503, "O pagamento ainda não está disponível.")
    if user["plan"] == "owner":
        raise HTTPException(400, "A conta do dono não precisa de pagamento.")
    if not user["email_verified"]:
        raise HTTPException(403, "Confirme seu e-mail antes de pagar.")
    if auth.access(user)["plan"] == "active" and user.get("mp_status") == "authorized":
        raise HTTPException(400, "Sua assinatura no cartão já está ativa.")
    try:
        return billing.pix_create(user, tier)
    except Exception as e:  # noqa: BLE001
        _mp_error(e)


@app.post("/api/billing/pix/check")
def pix_check(body: PixCheckIn, user=Depends(current_user)):
    auth.rate_limit("pixchk:" + str(user["id"]), 240, 3600)
    if not billing.configured():
        return {"status": None}
    try:
        return billing.pix_confirm(db, body.payment_id, only_user=str(user["id"]))
    except Exception as e:  # noqa: BLE001
        _mp_error(e)


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    """Aviso do Mercado Pago. Só serve de gatilho: o status é sempre lido de novo na API."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    q = request.query_params
    kind = body.get("type") or q.get("type") or q.get("topic") or ""
    rid = str((body.get("data") or {}).get("id") or q.get("data.id") or q.get("id") or "")
    if not rid or not billing.configured() or not rid.replace("-", "").isalnum():
        return {"ok": True}
    try:
        if kind == "payment":
            await run_in_threadpool(billing.pix_confirm, db, rid)
            return {"ok": True}
        if "authorized_payment" in kind:
            pay = await run_in_threadpool(billing._call, "GET", "/authorized_payments/" + rid)
            rid = str(pay.get("preapproval_id") or "")
        if rid:
            pre = await run_in_threadpool(billing.get, rid)
            with db() as conn:
                billing.apply(conn, pre)
    except Exception as e:  # noqa: BLE001 - responder 200 evita reenvio infinito
        print("webhook Mercado Pago:", e)
    return {"ok": True}


@app.post("/api/me/delete")
def delete_account(body: Confirm, user=Depends(current_user)):
    if user["plan"] == "owner":
        raise HTTPException(400, "A conta do dono não pode ser excluída pelo app.")
    if not auth.check_password(body.password, user["pass_hash"]):
        raise HTTPException(401, "Senha incorreta.")
    if user.get("mp_preapproval_id") and user.get("mp_status") in ("authorized", "pending", "paused") and billing.configured():
        try:
            billing.cancel(user["mp_preapproval_id"])
        except Exception as e:  # noqa: BLE001
            if user.get("mp_status") == "authorized":
                raise HTTPException(502, "Não consegui cancelar sua assinatura no Mercado Pago agora. Tente de novo em alguns minutos.") from e
    with db() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (user["id"],))
    return {"ok": True}


@app.get("/api/admin/stats")
def admin_stats(user=Depends(current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Acesso restrito.")
    with db() as conn:
        u = conn.execute("""SELECT count(*) FILTER (WHERE plan <> 'owner') AS signups,
                                   count(*) FILTER (WHERE plan <> 'owner' AND email_verified) AS verified,
                                   count(*) FILTER (WHERE plan = 'trial' AND trial_ends_at > now()) AS trial_active,
                                   count(*) FILTER (WHERE plan = 'trial' AND trial_ends_at <= now()) AS trial_ended,
                                   count(*) FILTER (WHERE wants_subscription_at IS NOT NULL) AS want_to_pay,
                                   count(*) FILTER (WHERE plan IN ('active', 'canceled') AND paid_until > now()) AS paying
                            FROM users""").fetchone()
        a = conn.execute("""SELECT count(*) AS attempts_7d, count(DISTINCT user_id) AS active_users_7d,
                                   round(coalesce(sum(audio_ms), 0) / 60000.0) AS azure_min_7d,
                                   count(*) FILTER (WHERE used_llm) AS llm_calls_7d
                            FROM attempts WHERE created_at > now() - interval '7 days'""").fetchone()
        m = conn.execute("""SELECT round(coalesce(sum(audio_ms), 0) / 60000.0) AS azure_min_month FROM attempts
                            WHERE created_at >= date_trunc('month', now())""").fetchone()
    return {**u, **a, **m}


# ---------- conteúdo ----------

@app.get("/api/content/{level}")
def get_content(level: int, user=Depends(current_user)):
    if level not in (1, 2, 3, 4):
        raise HTTPException(404, "Nível ainda não disponível.")
    return {"level": level, "name": content.LEVEL_NAMES[level], "items": content.items_for_level(level, user.get("target_level"))}


# ---------- tentativas ----------

class AttemptIn(BaseModel):
    item_id: str
    transcript: str = Field(max_length=5000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    duration_ms: int | None = Field(default=None, ge=0, le=600000)


def streak_progress(conn, user_id, level):
    rows = conn.execute(
        "SELECT main_score FROM attempts WHERE user_id = %s AND level = %s ORDER BY created_at DESC LIMIT 5",
        (user_id, level)).fetchall()
    n = 0
    for r in rows:
        if float(r["main_score"]) >= 80:
            n += 1
        else:
            break
    return n


def update_reviews(conn, user_id, weak, ok):
    today = conn.execute(f"SELECT (now() AT TIME ZONE '{TZ}')::date AS d").fetchone()["d"]
    for w in set(weak):
        conn.execute(
            """INSERT INTO review_items (user_id, word, interval_days, next_due, misses)
               VALUES (%s, %s, 1, %s + 1, 1)
               ON CONFLICT (user_id, word) DO UPDATE
               SET interval_days = 1, next_due = EXCLUDED.next_due,
                   misses = review_items.misses + 1, updated_at = now()""",
            (user_id, w, today))
    for w in set(ok) - set(weak):
        row = conn.execute(
            "SELECT interval_days FROM review_items WHERE user_id = %s AND word = %s AND next_due <= %s",
            (user_id, w, today)).fetchone()
        if not row:
            continue
        cur = row["interval_days"]
        nxt = next((i for i in INTERVALS if i > cur), None)
        if nxt is None:
            conn.execute("DELETE FROM review_items WHERE user_id = %s AND word = %s", (user_id, w))
        else:
            conn.execute(
                """UPDATE review_items SET interval_days = %s, next_due = %s + %s,
                   hits = hits + 1, updated_at = now() WHERE user_id = %s AND word = %s""",
                (nxt, today, nxt, user_id, w))


def save_attempt(user, level, item, transcript, result, engine, duration_ms, request_meta, audio_ms=None):
    s = result["scores"]
    with db() as conn:
        with conn.transaction():
            row = conn.execute(
                """INSERT INTO attempts (user_id, level, item_id, target_text, transcript, engine, main_score,
                       accuracy, completeness, confidence, fluency, duration_ms, word_count, raw, audio_ms, used_llm)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (user["id"], level, item["id"], item["text"], transcript, engine, result["main"],
                 s.get("accuracy"), s.get("completeness"), s.get("confidence"), s.get("fluency"), duration_ms,
                 len(transcript.split()),
                 json.dumps({"request": request_meta, "result": result}, ensure_ascii=False), audio_ms,
                 "llm" in result)).fetchone()
            for seq, w in enumerate(result["words"]):
                conn.execute(
                    """INSERT INTO attempt_words (attempt_id, seq, position, expected, heard, status, score)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (row["id"], seq, w["pos"], w["expected"], w["heard"], w["status"], w["score"]))
            if item["kind"] in ("word", "sentence"):
                update_reviews(conn, user["id"], result["weak"], result["ok"])

            level_up = None
            if level == user["level"] and level < MAX_LEVEL_BASIC and streak_progress(conn, user["id"], level) >= 5:
                conn.execute("UPDATE users SET level = level + 1 WHERE id = %s", (user["id"],))
                level_up = level + 1

    return {"attempt_id": row["id"], "level": level, "transcript": transcript, **result,
            "level_up": level_up, "level_up_name": content.LEVEL_NAMES.get(level_up) if level_up else None}


def add_llm(result, item, transcript, allowed=True):
    if not allowed:
        result["tips"] = [t for t in result["tips"] if "chave do LLM" not in t["text"]]
        result["tips"].append({"word": "", "ipa": "", "text": "Você chegou ao limite de correções com IA de hoje. Amanhã ele renova."})
        return result
    fb = llm.feedback(item["kind"], item["text"], transcript, item.get("keywords"))
    if not fb:
        return result
    result["llm"] = fb
    result["main"] = round((result["main"] + fb["score"]) / 2)
    result["scores"]["grammar"] = fb["score"]
    tips = [t for t in result["tips"] if "chave do LLM" not in t["text"]]
    if fb["tip"]:
        tips.insert(0, {"word": "", "ipa": "", "text": fb["tip"]})
    result["tips"] = tips
    result["drills"] = [{"id": "t:" + d, "text": d} for d in fb["drills"]]
    return result


@app.post("/api/attempts")
def create_attempt(body: AttemptIn, user=Depends(current_user)):
    plan = auth.require_practice(user)
    level, item = content.find_item(body.item_id)
    if not item:
        raise HTTPException(404, "Exercício não encontrado.")
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(422, "Nenhuma fala reconhecida. Tente de novo, mais perto do microfone.")

    if item["kind"] in ("word", "sentence"):
        result = score_repeat(item["text"], transcript, body.confidence)
        result["engine"] = "browser"
    else:
        result = score_open(item["kind"], transcript, body.duration_ms, item.get("keywords"))
        result["engine"] = "browser"
        with db() as conn:
            allowed = auth.llm_allowed(conn, user, plan)
        result = add_llm(result, item, transcript, allowed)
    return save_attempt(user, level, item, transcript, result, "browser", body.duration_ms, body.model_dump())


@app.post("/api/attempts/audio")
async def create_attempt_audio(request: Request, item_id: str, duration_ms: int | None = None,
                               user=Depends(current_user)):
    plan = auth.require_practice(user)
    if not azure_speech.configured():
        raise HTTPException(503, "A avaliação por fonema ainda não está configurada.")
    level, item = content.find_item(item_id)
    if not item or item["kind"] not in ("word", "sentence"):
        raise HTTPException(404, "Exercício não encontrado.")
    wav = await request.body()
    if len(wav) < 1000 or len(wav) > 4_000_000 or wav[:4] != b"RIFF":
        raise HTTPException(422, "Gravação inválida. Tente de novo.")
    audio_ms = (len(wav) - 44) // 32
    limit = auth.audio_limit_ms(plan, user.get("tier"))
    if limit is not None:
        with db() as conn:
            used = auth.audio_used_ms(conn, user, plan)
        if used + audio_ms > limit:
            raise HTTPException(402, f"Você usou os {limit // 60000} minutos de áudio avaliado do seu plano. "
                                     "Os níveis 3 e 4 continuam disponíveis.")
    try:
        nb = await run_in_threadpool(azure_speech.assess, wav, item["text"])
    except azure_speech.AzureError as e:
        raise HTTPException(502, str(e))
    result = azure_speech.score_azure(item["text"], nb)
    transcript = result.pop("transcript") or "(sem transcrição)"
    meta = {"item_id": item_id, "duration_ms": duration_ms, "audio_bytes": len(wav)}
    return await run_in_threadpool(save_attempt, user, level, item, transcript, result, "azure", duration_ms, meta, audio_ms)


# ---------- treino por som ----------

@app.get("/api/sounds")
def sounds(user=Depends(current_user)):
    from .phonemes import DRILLS, tip_for
    with db() as conn:
        rows = conn.execute(
            """SELECT phoneme, n, avg_score FROM phoneme_stats
               WHERE user_id = %s AND n >= 3 ORDER BY avg_score, n DESC""", (user["id"],)).fetchall()
    has_data = bool(rows)
    rows = [r for r in rows if float(r["avg_score"]) < 80]
    out = []
    for r in rows:
        ph = r["phoneme"]
        items = content.words_with_phoneme(ph)[:6]
        items += [{"id": "t:" + t, "text": t, "kind": "sentence", "hint": "Frase para treinar o som /" + ph + "/."}
                  for t in DRILLS.get(ph, [])]
        if not items:
            continue
        for it in items:
            it["label"] = "Som /" + ph + "/"
        out.append({"p": ph, "n": r["n"], "avg": round(float(r["avg_score"])), "tip": tip_for(ph), "items": items})
        if len(out) == 3:
            break
    return {"sounds": out, "has_data": has_data}


# ---------- painéis ----------

@app.get("/api/home")
def home(user=Depends(current_user)):
    uid = user["id"]
    with db() as conn:
        days = [r["d"] for r in conn.execute(
            f"""SELECT DISTINCT (created_at AT TIME ZONE '{TZ}')::date AS d FROM attempts
                WHERE user_id = %s ORDER BY d DESC LIMIT 400""", (uid,)).fetchall()]
        today = conn.execute(f"SELECT (now() AT TIME ZONE '{TZ}')::date AS d").fetchone()["d"]
        streak = 0
        if days and (today - days[0]).days <= 1:
            streak, prev = 1, days[0]
            for d in days[1:]:
                if (prev - d).days == 1:
                    streak, prev = streak + 1, d
                else:
                    break
        stats = conn.execute(
            f"""SELECT count(*) AS total,
                   count(*) FILTER (WHERE (created_at AT TIME ZONE '{TZ}')::date = %s) AS today,
                   round(avg(main_score) FILTER (WHERE created_at > now() - interval '7 days')) AS avg7
                FROM attempts WHERE user_id = %s""", (today, uid)).fetchone()
        due = conn.execute(
            """SELECT word, interval_days, misses FROM review_items
               WHERE user_id = %s AND next_due <= %s ORDER BY misses DESC, next_due LIMIT 8""",
            (uid, today)).fetchall()
        progress = streak_progress(conn, uid, user["level"])
        account = account_info(conn, user)
    return {
        "account": account,
        "name": user["name"], "level": user["level"], "level_name": content.LEVEL_NAMES[user["level"]],
        "streak": streak, "total": stats["total"], "today": stats["today"],
        "avg7": int(stats["avg7"]) if stats["avg7"] is not None else None,
        "to_next": {"done": progress, "needed": 5, "max_level": user["level"] >= MAX_LEVEL_BASIC},
        "review": [{"word": d["word"], "ipa": content.WORD_INDEX.get(d["word"], {}).get("ipa", ""),
                    "interval": d["interval_days"], "id": "r:" + d["word"]} for d in due],
    }


@app.get("/api/progress")
def progress(user=Depends(current_user)):
    uid = user["id"]
    with db() as conn:
        daily = conn.execute(
            f"""SELECT (created_at AT TIME ZONE '{TZ}')::date AS day, round(avg(main_score)) AS avg, count(*) AS n
                FROM attempts WHERE user_id = %s AND level IN (1, 2)
                  AND created_at > now() - interval '21 days'
                GROUP BY 1 ORDER BY 1""", (uid,)).fetchall()
        missed = conn.execute(
            """SELECT w.expected AS word, count(*) AS n
               FROM attempt_words w JOIN attempts a ON a.id = w.attempt_id
               WHERE a.user_id = %s AND w.status IN ('wrong', 'missing', 'close') AND w.expected IS NOT NULL
                 AND NOT (w.expected = ANY(%s))
               GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 6""", (uid, list(SHORT))).fetchall()
        by_level = conn.execute(
            """SELECT level, count(*) AS n, round(avg(main_score)) AS avg
               FROM attempts WHERE user_id = %s GROUP BY 1 ORDER BY 1""", (uid,)).fetchall()
    return {
        "daily": [{"day": r["day"].isoformat(), "avg": int(r["avg"]), "n": r["n"]} for r in daily],
        "missed": [{"word": r["word"], "n": r["n"], "ipa": content.WORD_INDEX.get(r["word"], {}).get("ipa", "")} for r in missed],
        "by_level": [{"level": r["level"], "name": content.LEVEL_NAMES[r["level"]], "n": r["n"], "avg": int(r["avg"])} for r in by_level],
    }


# ---------- front-end ----------

if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
