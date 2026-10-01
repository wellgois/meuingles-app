"""Pontuação do modo básico (reconhecimento de voz do navegador).

Compara a transcrição com a frase-alvo palavra por palavra. Não mede fonemas:
isso entra quando o Azure Speech for configurado (modo "azure").
"""
import re
from difflib import SequenceMatcher

from .content import SENTENCES, STAR_WORDS, WORD_INDEX

NUMBERS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
    "7": "seven", "8": "eight", "9": "nine", "10": "ten", "11": "eleven", "12": "twelve",
}
ALIASES = {"sequel": "sql", "pi": "py", "pie": "py"}
SHORT = {"the", "a", "an", "of", "to", "and", "in", "on", "at", "is", "it", "for", "we", "i"}


def words(text: str) -> list[str]:
    text = (text or "").lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    out = []
    for w in text.split():
        w = w.replace("'", "")
        w = NUMBERS.get(w, ALIASES.get(w, w))
        if w:
            out.append(w)
    return out


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def align(target: str, transcript: str):
    exp_display = re.findall(r"[A-Za-z0-9'’]+", target)
    exp = words(target)
    heard = words(transcript)
    # junta "py spark" -> "pyspark" quando o alvo tem a palavra composta
    joined = []
    i = 0
    while i < len(heard):
        if i + 1 < len(heard) and heard[i] + heard[i + 1] in exp:
            joined.append(heard[i] + heard[i + 1]); i += 2
        else:
            joined.append(heard[i]); i += 1
    heard = joined

    rows = []
    sm = SequenceMatcher(None, exp, heard, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append({"pos": i1 + k, "expected": exp[i1 + k], "heard": heard[j1 + k], "status": "ok", "score": 100})
        elif tag == "replace":
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                e = exp[i1 + k] if i1 + k < i2 else None
                h = heard[j1 + k] if j1 + k < j2 else None
                if e is None:
                    rows.append({"pos": None, "expected": None, "heard": h, "status": "extra", "score": None})
                elif h is None:
                    rows.append({"pos": i1 + k, "expected": e, "heard": None, "status": "missing", "score": 0})
                else:
                    r = _sim(e, h)
                    if r >= 0.8:
                        rows.append({"pos": i1 + k, "expected": e, "heard": h, "status": "close", "score": round(r * 100)})
                    else:
                        rows.append({"pos": i1 + k, "expected": e, "heard": h, "status": "wrong", "score": round(r * 60)})
        elif tag == "delete":
            for k in range(i1, i2):
                rows.append({"pos": k, "expected": exp[k], "heard": None, "status": "missing", "score": 0})
        elif tag == "insert":
            for k in range(j1, j2):
                rows.append({"pos": None, "expected": None, "heard": heard[k], "status": "extra", "score": None})

    for r in rows:
        if r["pos"] is not None and r["pos"] < len(exp_display):
            r["display"] = exp_display[r["pos"]]
        else:
            r["display"] = r["heard"] or r["expected"] or ""
    return exp, heard, rows


def score_repeat(target: str, transcript: str, confidence: float | None):
    exp, heard, rows = align(target, transcript)
    scored = [r for r in rows if r["expected"] is not None]
    n = max(len(exp), 1)
    accuracy = round(sum(r["score"] for r in scored) / n)
    missing = sum(1 for r in scored if r["status"] == "missing")
    completeness = round((n - missing) / n * 100)
    conf = round(confidence * 100) if confidence is not None else None

    tips, seen = [], set()
    weak = [r for r in scored if r["status"] in ("wrong", "missing", "close")]
    for r in weak:
        key = r["expected"]
        info = WORD_INDEX.get(key)
        if info and key not in seen:
            seen.add(key)
            heard_txt = f" O reconhecedor ouviu \"{r['heard']}\"." if r["heard"] else " A palavra não foi reconhecida."
            tips.append({"word": r["display"], "ipa": info["ipa"], "text": info["tip"] + heard_txt})
    for r in weak:
        key = r["expected"]
        if key in seen or key in WORD_INDEX:
            continue
        seen.add(key)
        if key in SHORT:
            tips.append({"word": r["display"], "ipa": "", "text": "Palavras curtas como the, a, of e to são fracas no inglês, mas precisam aparecer. Não as engula."})
        elif r["heard"]:
            tips.append({"word": r["display"], "ipa": "", "text": f"Saiu como \"{r['heard']}\". Ouça a frase de novo e repita só essa palavra três vezes."})
        else:
            tips.append({"word": r["display"], "ipa": "", "text": "Essa palavra não foi reconhecida. Fale um pouco mais devagar e articule o final dela."})
        if len(tips) >= 4:
            break
    if not weak:
        tips.append({"word": "", "ipa": "", "text": "Todas as palavras foram reconhecidas. Tente agora no ritmo do áudio, ligando as palavras."})

    drills = drills_for([r["expected"] for r in weak])
    return {
        "scores": {"accuracy": accuracy, "completeness": completeness, "confidence": conf},
        "main": accuracy,
        "words": rows,
        "tips": tips[:4],
        "drills": drills,
        "weak": [r["expected"] for r in weak if r["expected"] not in SHORT],
        "ok": [r["expected"] for r in scored if r["status"] == "ok"],
    }


def drills_for(weak_words: list[str]) -> list[dict]:
    """Frases do banco que contêm as palavras fracas; se não houver, a própria palavra."""
    out, texts = [], set()
    for w in weak_words:
        if w in SHORT:
            continue
        for sid, s in SENTENCES:
            if w in words(s) and s not in texts:
                out.append({"id": sid, "text": s}); texts.add(s)
                break
        if len(out) >= 3:
            break
    for w in weak_words:
        if len(out) >= 3:
            break
        if w in WORD_INDEX and w not in texts:
            out.append({"id": "r:" + w, "text": w}); texts.add(w)
    return out[:3]


def score_open(kind: str, transcript: str, duration_ms: int | None, keywords: list[str] | None):
    ws = words(transcript)
    n = len(ws)
    minutes = (duration_ms or 0) / 60000
    wpm = round(n / minutes) if minutes > 0.05 else None
    text = " " + " ".join(ws) + " "
    tips = []
    if kind == "explain":
        kws = keywords or []
        used = [k for k in kws if f" {k}" in text]
        coverage = round(len(used) / max(len(kws), 1) * 100)
        main = coverage
        if minutes and minutes < 0.6:
            tips.append({"word": "", "ipa": "", "text": "Resposta curta. Tente falar pelo menos 45 segundos explicando com um exemplo."})
        missing = [k for k in kws if k not in used]
        if missing:
            tips.append({"word": "", "ipa": "", "text": "Termos que faltaram: " + ", ".join(missing) + "."})
        detail = {"keywords_used": used, "keywords_missing": missing}
    else:
        parts = {p: any(f" {w} " in text for w in cues) for p, cues in STAR_WORDS.items()}
        main = round(sum(parts.values()) / 4 * 100)
        names = {"situation": "Situação", "task": "Tarefa", "action": "Ação (comece com \"I built\", \"I decided\")", "result": "Resultado com número"}
        faltam = [names[p] for p, ok in parts.items() if not ok]
        if faltam:
            tips.append({"word": "", "ipa": "", "text": "Parte da estrutura STAR que não apareceu: " + "; ".join(faltam) + "."})
        if minutes and minutes < 1.2:
            tips.append({"word": "", "ipa": "", "text": "Respostas de entrevista costumam ter de 90 a 120 segundos."})
        detail = {"star": parts}
    if wpm and wpm < 90:
        tips.append({"word": "", "ipa": "", "text": f"Ritmo de {wpm} palavras por minuto. Uma conversa costuma ficar entre 120 e 150."})
    tips.append({"word": "", "ipa": "", "text": "A correção de gramática e a versão mais natural da sua resposta entram quando a chave do LLM for configurada."})
    return {
        "scores": {"coverage": main, "words": n, "wpm": wpm},
        "main": main,
        "words": [],
        "tips": tips,
        "drills": [],
        "weak": [],
        "ok": [],
        "detail": detail,
    }
