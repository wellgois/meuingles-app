"""Correção de fala livre (níveis 3 e 4) com um LLM. Hoje: Anthropic (Claude)."""
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request

log = logging.getLogger("meuingles.llm")
_tl = threading.local()
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SYSTEM = """You are an English speaking coach for a Brazilian data engineer preparing for job interviews.
You receive an interview-style question and the learner's spoken answer, transcribed by speech recognition
(so small recognition errors are possible; do not penalize obvious transcription noise).
Reply with ONLY a JSON object, no markdown, with exactly these keys:
"score": integer 0-100 for grammar, clarity and technical vocabulary of the spoken answer;
"errors": up to 4 objects {"wrong": exact short excerpt, "right": corrected excerpt, "why": short explanation in Brazilian Portuguese};
"natural": a more natural spoken version of the same answer in English, keeping the learner's content, at most 90 words;
"drills": exactly 3 short English sentences (max 14 words each) that practice the learner's weakest points, about data engineering;
"tip": one sentence in Brazilian Portuguese with the single most important improvement."""


def configured() -> bool:
    return os.environ.get("LLM_PROVIDER") == "anthropic" and bool(os.environ.get("LLM_API_KEY"))


def _call_anthropic(user_text: str) -> str:
    body = {
        "model": os.environ.get("LLM_MODEL") or DEFAULT_MODEL,
        "max_tokens": 900,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": user_text}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"x-api-key": os.environ["LLM_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _tl.usage = data.get("usage") or {}
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _parse(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    try:
        score = max(0, min(100, int(d.get("score", 0))))
    except (TypeError, ValueError):
        return None
    errors = []
    for e in (d.get("errors") or [])[:4]:
        if isinstance(e, dict) and e.get("wrong") and e.get("right"):
            errors.append({"wrong": str(e["wrong"])[:200], "right": str(e["right"])[:200], "why": str(e.get("why", ""))[:300]})
    drills = [str(s)[:160] for s in (d.get("drills") or []) if isinstance(s, str) and s.strip()][:3]
    return {"score": score, "errors": errors, "natural": str(d.get("natural", ""))[:900],
            "drills": drills, "tip": str(d.get("tip", ""))[:300]}


def feedback(kind: str, question: str, transcript: str, keywords: list[str] | None = None) -> dict | None:
    """Devolve a correção ou None (sem chave, erro de rede ou resposta inválida)."""
    if not configured():
        return None
    extra = f"\nTechnical terms the answer should ideally use: {', '.join(keywords)}." if keywords else ""
    if kind == "star":
        extra += "\nThis is a behavioral question: also check the STAR structure (Situation, Task, Action, Result with a number)."
    user_text = f"Question: {question}{extra}\n\nLearner's spoken answer (transcribed):\n{transcript[:4000]}"
    try:
        _tl.usage = {}
        fb = _parse(_call_anthropic(user_text))
        if fb is not None:
            u = getattr(_tl, "usage", None) or {}
            fb["usage"] = {"in": int(u.get("input_tokens", 0) or 0), "out": int(u.get("output_tokens", 0) or 0)}
        return fb
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
        log.warning("LLM indisponível: %s", e)
        return None
