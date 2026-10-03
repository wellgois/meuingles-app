"""Checagens de qualidade rodadas ANTES de gravar: se alguma falhar, nada é publicado."""
import re

import pyarrow as pa

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
KEY_RE = re.compile(r"^[0-9a-f]{32}$")
KEY_COLS = {"user_key", "visitor_key", "session_key", "pageview_key"}
RANGES = [("attempts", "main_score"), ("attempts", "accuracy"), ("attempts", "completeness"),
          ("attempts", "fluency"), ("attempt_words", "score"), ("attempt_phonemes", "score")]
UNIQUE = {"attempts": ["attempt_id"], "attempt_words": ["attempt_id", "seq"],
          "attempt_phonemes": ["attempt_id", "word_seq", "phoneme_seq"], "visits": ["pageview_key"],
          "users": ["user_key"], "review_items": ["user_key", "word"], "deleted_users": ["user_key"]}


def _col(tables, tname, col):
    t = tables.get(tname)
    return t.column(col).to_pylist() if t is not None and col in t.column_names else None


def check_tables(tables: dict) -> list[str]:
    fails = []
    # nenhum dado pessoal e nenhum identificador cru nas colunas de texto
    for tname, t in tables.items():
        for f in t.schema:
            if not pa.types.is_string(f.type):
                continue
            vals = [v for v in t.column(f.name).to_pylist() if v is not None]
            if f.name in KEY_COLS:
                if any(not KEY_RE.match(v) for v in vals):
                    fails.append(f"{tname}.{f.name}: pseudônimo fora do formato esperado")
            else:
                if any(EMAIL_RE.search(v) for v in vals):
                    fails.append(f"{tname}.{f.name}: possível e-mail")
                if any(UUID_RE.match(v) for v in vals):
                    fails.append(f"{tname}.{f.name}: identificador cru (UUID)")
    # notas entre 0 e 100
    for tname, col in RANGES:
        v = _col(tables, tname, col)
        if v and any(x is not None and not 0 <= x <= 100 for x in v):
            fails.append(f"{tname}.{col}: valor fora de 0-100")
    lv = _col(tables, "attempts", "level")
    if lv and any(x is None or not 1 <= x <= 5 for x in lv):
        fails.append("attempts.level: fora de 1-5")
    en = _col(tables, "attempts", "engine")
    if en and any(x not in ("browser", "azure") for x in en):
        fails.append("attempts.engine: valor desconhecido")
    # chaves únicas
    for tname, cols in UNIQUE.items():
        t = tables.get(tname)
        if t is None or not all(c in t.column_names for c in cols):
            continue
        rows = list(zip(*[t.column(c).to_pylist() for c in cols]))
        if len(rows) != len(set(rows)):
            fails.append(f"{tname}: chave duplicada ({', '.join(cols)})")
    # palavras e fonemas sem tentativa (órfãos)
    ids = _col(tables, "attempts", "attempt_id")
    if ids is not None:
        known = set(ids)
        for tname in ("attempt_words", "attempt_phonemes"):
            v = _col(tables, tname, "attempt_id")
            if v and any(x not in known for x in v):
                fails.append(f"{tname}: linhas sem tentativa correspondente")
    return fails
