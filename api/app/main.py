import hmac
import json
import os
import time
import uuid
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from . import azure_speech, content, llm
from .scoring import SHORT, score_open, score_repeat

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost/meuingles")
ACCESS_CODE = os.environ.get("APP_ACCESS_CODE", "")
WEB_DIR = Path(os.environ.get("WEB_DIR", Path(__file__).resolve().parents[2] / "web"))
TZ = "America/Sao_Paulo"
INTERVALS = [1, 3, 7, 14, 30]
MAX_LEVEL_BASIC = 4

app = FastAPI(title="MeuInglês API", docs_url="/api/docs", openapi_url="/api/openapi.json")


def db():
    return psycopg.connect(DB_URL, row_factory=dict_row, autocommit=True)


@app.on_event("startup")
def init_schema():
    sql = (Path(__file__).parent / "schema.sql").read_text()
    for attempt in range(30):
        try:
            with db() as conn:
                conn.execute(sql)
            return
        except psycopg.OperationalError:
            time.sleep(2)
    raise RuntimeError("Banco de dados indisponível depois de 60 s")


def current_user(x_user_id: str = Header(""), x_access_code: str = Header("")):
    if not ACCESS_CODE or not hmac.compare_digest(x_access_code, ACCESS_CODE):
        raise HTTPException(401, "Código de acesso inválido.")
    try:
        uid = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(401, "Usuário não identificado. Entre novamente.")
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = %s", (uid,)).fetchone()
    if not user:
        raise HTTPException(401, "Usuário não encontrado. Entre novamente.")
    return user


# ---------- públicos ----------

@app.get("/api/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "engine": "azure" if azure_speech.configured() else "browser",
            "azure_configured": azure_speech.configured(), "llm_configured": llm.configured()}


class SignIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    access_code: str
    user_id: str | None = None


@app.post("/api/signin")
def signin(body: SignIn):
    if not ACCESS_CODE or not hmac.compare_digest(body.access_code, ACCESS_CODE):
        raise HTTPException(401, "Código de acesso inválido.")
    with db() as conn:
        if body.user_id:
            try:
                row = conn.execute("SELECT id FROM users WHERE id = %s", (uuid.UUID(body.user_id),)).fetchone()
            except ValueError:
                row = None
            if row:
                conn.execute("UPDATE users SET name = %s WHERE id = %s", (body.name.strip(), row["id"]))
                return {"user_id": str(row["id"])}
        uid = uuid.uuid4()
        conn.execute("INSERT INTO users (id, name) VALUES (%s, %s)", (uid, body.name.strip()))
    return {"user_id": str(uid)}


# ---------- conteúdo ----------

@app.get("/api/content/{level}")
def get_content(level: int, user=Depends(current_user)):
    if level not in (1, 2, 3, 4):
        raise HTTPException(404, "Nível ainda não disponível.")
    return {"level": level, "name": content.LEVEL_NAMES[level], "items": content.items_for_level(level)}


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


def save_attempt(user, level, item, transcript, result, engine, duration_ms, request_meta):
    s = result["scores"]
    with db() as conn:
        with conn.transaction():
            row = conn.execute(
                """INSERT INTO attempts (user_id, level, item_id, target_text, transcript, engine, main_score,
                       accuracy, completeness, confidence, fluency, duration_ms, word_count, raw)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (user["id"], level, item["id"], item["text"], transcript, engine, result["main"],
                 s.get("accuracy"), s.get("completeness"), s.get("confidence"), s.get("fluency"), duration_ms,
                 len(transcript.split()),
                 json.dumps({"request": request_meta, "result": result}, ensure_ascii=False))).fetchone()
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


def add_llm(result, item, transcript):
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
        result = add_llm(result, item, transcript)
    return save_attempt(user, level, item, transcript, result, "browser", body.duration_ms, body.model_dump())


@app.post("/api/attempts/audio")
async def create_attempt_audio(request: Request, item_id: str, duration_ms: int | None = None,
                               user=Depends(current_user)):
    if not azure_speech.configured():
        raise HTTPException(503, "A avaliação por fonema ainda não está configurada.")
    level, item = content.find_item(item_id)
    if not item or item["kind"] not in ("word", "sentence"):
        raise HTTPException(404, "Exercício não encontrado.")
    wav = await request.body()
    if len(wav) < 1000 or len(wav) > 4_000_000 or wav[:4] != b"RIFF":
        raise HTTPException(422, "Gravação inválida. Tente de novo.")
    try:
        nb = await run_in_threadpool(azure_speech.assess, wav, item["text"])
    except azure_speech.AzureError as e:
        raise HTTPException(502, str(e))
    result = azure_speech.score_azure(item["text"], nb)
    transcript = result.pop("transcript") or "(sem transcrição)"
    meta = {"item_id": item_id, "duration_ms": duration_ms, "audio_bytes": len(wav)}
    return await run_in_threadpool(save_attempt, user, level, item, transcript, result, "azure", duration_ms, meta)


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
    return {
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
