"""Avaliação de pronúncia com o Azure Speech (REST para áudio curto, até 30 s)."""
import base64
import json
import os
import re
import urllib.error
import urllib.request

from .content import WORD_INDEX
from .phonemes import tip_for, to_ipa
from .scoring import SHORT, drills_for, words


class AzureError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))


def assess(wav: bytes, reference_text: str) -> dict:
    """Envia o WAV (PCM 16 kHz mono) e devolve o primeiro item de NBest."""
    full = {"ReferenceText": reference_text, "GradingSystem": "HundredMark", "Granularity": "Phoneme",
            "Dimension": "Comprehensive", "EnableMiscue": "True", "EnableProsodyAssessment": "True"}
    try:
        return _assess(wav, full)
    except AzureError as e:
        if "HTTP 400" not in str(e):
            raise
    # alguma opção recusada: tenta de novo só com o essencial
    return _assess(wav, {"ReferenceText": reference_text, "GradingSystem": "HundredMark", "Granularity": "Phoneme"})


def _assess(wav: bytes, params: dict) -> dict:
    region = os.environ["AZURE_SPEECH_REGION"]
    key = os.environ["AZURE_SPEECH_KEY"]
    url = (f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/"
           "cognitiveservices/v1?language=en-US&format=detailed")
    header = base64.b64encode(json.dumps(params).encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, data=wav, method="POST", headers={
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
        "Accept": "application/json",
        "Pronunciation-Assessment": header,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AzureError(f"O Azure respondeu HTTP {e.code}.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise AzureError("Não consegui falar com o Azure. Tente de novo em instantes.") from e
    status = data.get("RecognitionStatus")
    if status != "Success" or not data.get("NBest"):
        raise AzureError("Não reconheci fala nessa gravação. Fale um pouco mais alto e perto do microfone.")
    return data["NBest"][0]


def _pa(obj: dict) -> dict:
    """Os campos de nota podem vir no próprio objeto ou dentro de PronunciationAssessment."""
    inner = obj.get("PronunciationAssessment")
    return inner if isinstance(inner, dict) else obj


def _round(v):
    return None if v is None else round(float(v))


def score_azure(target: str, nb: dict) -> dict:
    top = _pa(nb)
    display = re.findall(r"[A-Za-z0-9'’]+", target)
    rows, pos = [], 0
    for w in nb.get("Words", []):
        pa = _pa(w)
        acc = _round(pa.get("AccuracyScore"))
        err = pa.get("ErrorType", "None")
        norm = (words(w.get("Word", "")) or [w.get("Word", "").lower()])[0]
        phon = []
        for ph in w.get("Phonemes", []) or []:
            sc = _round(_pa(ph).get("AccuracyScore"))
            phon.append({"p": to_ipa(ph.get("Phoneme", "")), "score": sc})
        if err == "Insertion":
            rows.append({"pos": None, "expected": None, "heard": norm, "status": "extra", "score": None,
                         "display": w.get("Word", ""), "phonemes": phon})
            continue
        if err == "Omission":
            status, acc = "missing", 0
        elif err == "Mispronunciation":
            status = "wrong" if (acc or 0) < 60 else "close"
        else:
            status = "ok" if (acc or 0) >= 80 else "close" if (acc or 0) >= 60 else "wrong"
        disp = display[pos] if pos < len(display) else w.get("Word", "")
        rows.append({"pos": pos, "expected": norm, "heard": None if status == "missing" else norm,
                     "status": status, "score": acc, "display": disp, "phonemes": phon})
        pos += 1

    scores = {"pron": _round(top.get("PronScore")), "accuracy": _round(top.get("AccuracyScore")),
              "fluency": _round(top.get("FluencyScore")), "completeness": _round(top.get("CompletenessScore")),
              "prosody": _round(top.get("ProsodyScore"))}
    main = scores["pron"] if scores["pron"] is not None else (scores["accuracy"] or 0)

    weak = [r for r in rows if r["status"] in ("wrong", "missing", "close")]
    weak.sort(key=lambda r: r["score"] if r["score"] is not None else 0)
    tips, seen_ph = [], set()
    for r in weak[:3]:
        info = WORD_INDEX.get(r["expected"], {})
        ipa = info.get("ipa") or ("/" + "".join(p["p"] for p in r["phonemes"]) + "/" if r["phonemes"] else "")
        if r["status"] == "missing":
            tips.append({"word": r["display"], "ipa": ipa, "text": "Essa palavra não apareceu na gravação. Fale a frase inteira, sem pular palavras."})
            continue
        bad = sorted([p for p in r["phonemes"] if p["score"] is not None and p["score"] < 70], key=lambda p: p["score"])
        parts = []
        for p in bad[:2]:
            t = tip_for(p["p"])
            if t and p["p"] not in seen_ph:
                seen_ph.add(p["p"])
                parts.append(f"/{p['p']}/ ({p['score']}): {t}")
        if not parts and bad:
            parts.append("Sons mais fracos: " + ", ".join(f"/{p['p']}/ {p['score']}" for p in bad[:3]) + ".")
        if not parts and info.get("tip"):
            parts.append(info["tip"])
        if parts:
            tips.append({"word": r["display"], "ipa": ipa, "text": " ".join(parts)})
    if scores["fluency"] is not None and scores["fluency"] < 70:
        tips.append({"word": "", "ipa": "", "text": f"Fluência {scores['fluency']}: fale a frase de uma vez, ligando as palavras, sem pausa entre elas."})
    if not tips:
        tips.append({"word": "", "ipa": "", "text": "Todos os sons ficaram bons. Tente agora um pouco mais rápido, no ritmo do áudio."})

    weak_words = [r["expected"] for r in weak if r["expected"] not in SHORT]
    return {
        "engine": "azure",
        "scores": scores,
        "main": main,
        "words": rows,
        "tips": tips[:4],
        "drills": drills_for([r["expected"] for r in weak]),
        "weak": weak_words,
        "ok": [r["expected"] for r in rows if r["status"] == "ok"],
        "transcript": nb.get("Display") or nb.get("Lexical") or "",
    }
