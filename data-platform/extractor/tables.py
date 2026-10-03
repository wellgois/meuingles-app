"""Tabelas exportadas: consulta SQL, pseudonimização e esquema Parquet de cada uma."""
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

import pyarrow as pa

from . import pseudo

STR, I32, I64, F64, BOOL = pa.string(), pa.int32(), pa.int64(), pa.float64(), pa.bool_()
TS = pa.timestamp("us", tz="UTC")
DATE = pa.date32()

DAY = "a.created_at >= %(start)s AND a.created_at < %(end)s"


@dataclass(frozen=True)
class Spec:
    kind: str                     # "daily" (partição dt=) ou "snapshot"
    sql: str
    schema: list
    keys: dict = field(default_factory=dict)   # coluna de origem -> coluna pseudonimizada


SPECS = {
    "attempts": Spec(
        "daily",
        f"""SELECT a.id AS attempt_id, a.user_id, a.created_at, a.level, a.item_id, a.engine,
                   a.main_score, a.accuracy, a.completeness, a.confidence, a.fluency,
                   a.duration_ms, a.audio_ms, a.word_count, a.used_llm,
                   (a.raw->'result'->'llm'->'usage'->>'in')::int AS llm_in_tokens,
                   (a.raw->'result'->'llm'->'usage'->>'out')::int AS llm_out_tokens
            FROM attempts a WHERE {DAY} ORDER BY a.id""",
        [("attempt_id", I64), ("user_key", STR), ("created_at", TS), ("level", I32), ("item_id", STR),
         ("engine", STR), ("main_score", F64), ("accuracy", F64), ("completeness", F64),
         ("confidence", F64), ("fluency", F64), ("duration_ms", I32), ("audio_ms", I32),
         ("word_count", I32), ("used_llm", BOOL), ("llm_in_tokens", I32), ("llm_out_tokens", I32)],
        {"user_id": "user_key"}),
    "attempt_words": Spec(
        "daily",
        f"""SELECT w.attempt_id, w.seq, w.position, w.expected, w.heard, w.status, w.score,
                   a.created_at AS attempt_created_at
            FROM attempt_words w JOIN attempts a ON a.id = w.attempt_id
            WHERE {DAY} AND a.level IN (1, 2) ORDER BY w.attempt_id, w.seq""",
        [("attempt_id", I64), ("seq", I32), ("position", I32), ("expected", STR), ("heard", STR),
         ("status", STR), ("score", F64), ("attempt_created_at", TS)]),
    "attempt_phonemes": Spec(
        "daily",
        f"""SELECT a.id AS attempt_id, (w.w_i - 1)::int AS word_seq, (p.p_i - 1)::int AS phoneme_seq,
                   p.ph->>'p' AS phoneme, (p.ph->>'score')::numeric AS score, a.created_at AS attempt_created_at
            FROM attempts a
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(a.raw->'result'->'words', '[]'::jsonb))
                  WITH ORDINALITY AS w(word, w_i)
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(w.word->'phonemes', '[]'::jsonb))
                  WITH ORDINALITY AS p(ph, p_i)
            WHERE {DAY} AND a.engine = 'azure' AND a.level IN (1, 2) AND p.ph->>'score' IS NOT NULL
            ORDER BY a.id, w.w_i, p.p_i""",
        [("attempt_id", I64), ("word_seq", I32), ("phoneme_seq", I32), ("phoneme", STR),
         ("score", F64), ("attempt_created_at", TS)]),
    "visits": Spec(
        "daily",
        f"""SELECT a.pv, a.vid, a.sid, a.created_at, a.updated_at, a.path, a.ref_host, a.utm_source,
                   a.utm_medium, a.utm_campaign, a.utm_content, a.device, a.inapp, a.is_new,
                   a.dur_s, a.max_scroll, a.clicked_cta
            FROM visits a WHERE {DAY} ORDER BY a.created_at""",
        [("pageview_key", STR), ("visitor_key", STR), ("session_key", STR), ("created_at", TS),
         ("updated_at", TS), ("path", STR), ("ref_host", STR), ("utm_source", STR), ("utm_medium", STR),
         ("utm_campaign", STR), ("utm_content", STR), ("device", STR), ("inapp", STR), ("is_new", BOOL),
         ("dur_s", I32), ("max_scroll", I32), ("clicked_cta", BOOL)],
        {"pv": "pageview_key", "vid": "visitor_key", "sid": "session_key"}),
    "users": Spec(
        "snapshot",
        """SELECT id AS user_id, signup_vid, level, plan, target_level, email_verified, created_at,
                  trial_ends_at, paid_until, sub_started_at, mp_status, wants_subscription_at,
                  signup_source, signup_campaign, signup_content, (plan = 'owner') AS is_owner, is_admin
           FROM users ORDER BY created_at""",
        [("user_key", STR), ("visitor_key", STR), ("level", I32), ("plan", STR), ("target_level", STR),
         ("email_verified", BOOL), ("created_at", TS), ("trial_ends_at", TS), ("paid_until", TS),
         ("sub_started_at", TS), ("mp_status", STR), ("wants_subscription_at", TS),
         ("signup_source", STR), ("signup_campaign", STR), ("signup_content", STR),
         ("is_owner", BOOL), ("is_admin", BOOL)],
        {"user_id": "user_key", "signup_vid": "visitor_key"}),
    "review_items": Spec(
        "snapshot",
        """SELECT user_id, word, interval_days, next_due, misses, hits, updated_at
           FROM review_items ORDER BY user_id, word""",
        [("user_key", STR), ("word", STR), ("interval_days", I32), ("next_due", DATE),
         ("misses", I32), ("hits", I32), ("updated_at", TS)],
        {"user_id": "user_key"}),
    "deleted_users": Spec(
        "snapshot",
        "SELECT user_id, signup_vid, deleted_at FROM deleted_users ORDER BY deleted_at",
        [("user_key", STR), ("visitor_key", STR), ("deleted_at", TS)],
        {"user_id": "user_key", "signup_vid": "visitor_key"}),
}

DAILY = [n for n, s in SPECS.items() if s.kind == "daily"]
SNAPSHOT = [n for n, s in SPECS.items() if s.kind == "snapshot"]


def _conv(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, dt.datetime):
        return v.astimezone(dt.timezone.utc)
    return v


def to_table(rows, spec, key):
    out = []
    for r in rows:
        r = dict(r)
        for src, dst in spec.keys.items():
            r[dst] = pseudo.pseudo(key, r.pop(src, None))
        out.append({name: _conv(r.get(name)) for name, _ in spec.schema})
    return pa.Table.from_pylist(out, schema=pa.schema(spec.schema))
