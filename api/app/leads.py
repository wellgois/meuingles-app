"""Painel de leads e estatísticas comerciais (somente administradores)."""
import os

from fastapi import Depends, HTTPException, Query

TZ = "America/Sao_Paulo"
PRICE = float(os.environ.get("PLAN_PRICE", "29.90"))
TRIAL_AUDIO_MIN = int(os.environ.get("TRIAL_AUDIO_MIN", "120"))
NEAR_MIN = round(0.8 * TRIAL_AUDIO_MIN, 1)
NEAR_MS = int(0.8 * TRIAL_AUDIO_MIN * 60000)

TRIAL_ACTIVE = "(u.plan = 'trial' AND (u.trial_ends_at IS NULL OR u.trial_ends_at > now()))"
PAYING_NOW = "(u.plan IN ('active', 'canceled') AND u.paid_until > now())"
PAID_EVER = "(u.plan IN ('active', 'canceled') OR u.paid_until IS NOT NULL)"
EXPIRED = f"(NOT {TRIAL_ACTIVE} AND u.plan NOT IN ('active', 'canceled'))"

LEADS_SQL = """
SELECT u.id, u.name, u.email, u.email_verified, u.plan, u.level, u.target_level, u.created_at,
       u.trial_ends_at, u.paid_until, u.mp_status, u.wants_subscription_at,
       u.signup_source, u.signup_campaign, u.signup_content,
       coalesce(s.n, 0) AS attempts, s.first_at, s.last_at,
       coalesce(s.azure_min, 0) AS azure_min, s.avg_score,
       CASE WHEN u.plan IN ('active', 'canceled') AND u.paid_until > now() THEN 'paying'
            WHEN u.plan IN ('active', 'canceled') THEN 'churned'
            WHEN u.plan = 'trial' AND (u.trial_ends_at IS NULL OR u.trial_ends_at > now()) THEN 'trial'
            ELSE 'expired' END AS segment
FROM users u
LEFT JOIN (SELECT user_id, count(*) AS n, min(created_at) AS first_at, max(created_at) AS last_at,
                  round(coalesce(sum(audio_ms) FILTER (WHERE engine = 'azure'), 0) / 60000.0, 1) AS azure_min,
                  round(avg(main_score), 1) AS avg_score
           FROM attempts GROUP BY user_id) s ON s.user_id = u.id
WHERE u.plan <> 'owner'
"""

SEGMENTS = {
    "all": "true",
    "trial": "t.segment = 'trial'",
    "trial_expiring": "t.segment = 'trial' AND t.trial_ends_at <= now() + interval '2 days'",
    "trial_inactive": "t.segment = 'trial' AND t.created_at < now() - interval '3 days' AND (t.last_at IS NULL OR t.last_at < now() - interval '3 days')",
    "near_quota": f"t.segment = 'trial' AND t.azure_min >= {NEAR_MIN}",
    "expired": "t.segment = 'expired'",
    "expired_engaged": "t.segment = 'expired' AND t.attempts >= 3",
    "paying": "t.segment = 'paying'",
    "churned": "t.segment = 'churned'",
    "unverified": "NOT t.email_verified",
    "want_to_pay": "t.wants_subscription_at IS NOT NULL AND t.segment <> 'paying'",
    "never_practiced": "t.attempts = 0",
}

ORDERS = {"created_at": "t.created_at", "last_at": "t.last_at", "attempts": "t.attempts",
          "trial_ends_at": "t.trial_ends_at", "azure_min": "t.azure_min"}


def register(app, db, current_user):
    def admin_only(user=Depends(current_user)):
        if not user["is_admin"]:
            raise HTTPException(403, "Acesso restrito.")
        return user

    @app.get("/api/admin/leads")
    def admin_leads(seg: str = "all", q: str = "", order: str = "created_at", desc: bool = True,
                    limit: int = Query(25, ge=1, le=2000), offset: int = Query(0, ge=0),
                    user=Depends(admin_only)):
        cond = SEGMENTS.get(seg)
        if cond is None:
            raise HTTPException(400, "Filtro inválido.")
        col = ORDERS.get(order, "t.created_at")
        where, params = [cond], []
        if q.strip():
            like = "%" + q.strip()[:80] + "%"
            where.append("(t.name ILIKE %s OR t.email ILIKE %s)")
            params += [like, like]
        w = " AND ".join(where)
        direction = "DESC" if desc else "ASC"
        with db() as conn:
            total = conn.execute(f"SELECT count(*) AS n FROM ({LEADS_SQL}) t WHERE {w}", params).fetchone()["n"]
            items = conn.execute(
                f"SELECT t.* FROM ({LEADS_SQL}) t WHERE {w} ORDER BY {col} {direction} NULLS LAST, t.created_at DESC "
                f"LIMIT %s OFFSET %s", params + [limit, offset]).fetchall()
            counts = conn.execute(
                "SELECT " + ", ".join(f'count(*) FILTER (WHERE {c}) AS "{k}"' for k, c in SEGMENTS.items())
                + f" FROM ({LEADS_SQL}) t").fetchone()
        return {"total": total, "items": items, "counts": counts}

    @app.get("/api/admin/insights")
    def admin_insights(user=Depends(admin_only)):
        with db() as conn:
            f = conn.execute(f"""
                WITH s AS (
                  SELECT user_id, count(*) AS n, min(created_at) AS first_at, max(created_at) AS last_at,
                         coalesce(sum(audio_ms) FILTER (WHERE engine = 'azure'), 0) AS azure_ms
                  FROM attempts GROUP BY user_id)
                SELECT count(*) AS signups,
                  count(*) FILTER (WHERE u.email_verified) AS verified,
                  count(*) FILTER (WHERE coalesce(s.n, 0) >= 1) AS practiced,
                  count(*) FILTER (WHERE coalesce(s.n, 0) >= 5) AS engaged,
                  count(*) FILTER (WHERE {PAID_EVER}) AS paid_ever,
                  count(*) FILTER (WHERE {PAYING_NOW}) AS paying_now,
                  count(*) FILTER (WHERE u.trial_ends_at <= now() OR {PAID_EVER}) AS trial_decided,
                  count(*) FILTER (WHERE s.first_at <= u.created_at + interval '24 hours') AS activated_24h,
                  round((avg(extract(epoch FROM (s.first_at - u.created_at)) / 3600.0))::numeric, 1) AS hours_to_first,
                  round((avg(extract(epoch FROM (coalesce(u.sub_started_at, u.mp_created_at) - u.created_at)) / 86400.0)
                         FILTER (WHERE coalesce(u.sub_started_at, u.mp_created_at) IS NOT NULL))::numeric, 1) AS days_to_pay,
                  count(*) FILTER (WHERE {TRIAL_ACTIVE} AND u.trial_ends_at <= now() + interval '2 days') AS trial_expiring,
                  count(*) FILTER (WHERE {TRIAL_ACTIVE} AND u.created_at < now() - interval '3 days' AND (s.last_at IS NULL OR s.last_at < now() - interval '3 days')) AS trial_inactive,
                  count(*) FILTER (WHERE {TRIAL_ACTIVE} AND coalesce(s.azure_ms, 0) >= {NEAR_MS}) AS near_quota,
                  count(*) FILTER (WHERE {EXPIRED} AND coalesce(s.n, 0) >= 3) AS expired_engaged,
                  count(*) FILTER (WHERE u.wants_subscription_at IS NOT NULL AND NOT {PAYING_NOW}) AS want_to_pay,
                  count(*) FILTER (WHERE NOT u.email_verified) AS unverified,
                  count(*) FILTER (WHERE u.created_at > now() - interval '7 days') AS signups_7d,
                  count(*) FILTER (WHERE u.created_at <= now() - interval '7 days'
                                   AND u.created_at > now() - interval '14 days') AS signups_prev_7d
                FROM users u LEFT JOIN s ON s.user_id = u.id
                WHERE u.plan <> 'owner'""").fetchone()
            act = conn.execute("""
                SELECT count(DISTINCT a.user_id) FILTER (WHERE a.created_at > now() - interval '7 days') AS active_7d,
                       count(DISTINCT a.user_id) FILTER (WHERE a.created_at <= now() - interval '7 days') AS active_prev_7d
                FROM attempts a JOIN users u ON u.id = a.user_id
                WHERE u.plan <> 'owner' AND a.created_at > now() - interval '14 days'""").fetchone()
            by_day = conn.execute(f"""
                SELECT to_char(d, 'YYYY-MM-DD') AS day, count(u.id) AS n
                FROM generate_series((now() AT TIME ZONE '{TZ}')::date - 29, (now() AT TIME ZONE '{TZ}')::date,
                                     interval '1 day') d
                LEFT JOIN users u ON (u.created_at AT TIME ZONE '{TZ}')::date = d::date AND u.plan <> 'owner'
                GROUP BY d ORDER BY d""").fetchall()
            by_track = conn.execute(f"""
                SELECT coalesce(u.target_level, 'sem trilha') AS k, count(*) AS n,
                       count(*) FILTER (WHERE {PAID_EVER}) AS paid
                FROM users u WHERE u.plan <> 'owner' GROUP BY 1 ORDER BY n DESC""").fetchall()
            by_level = conn.execute("""
                SELECT level AS k, count(*) AS n FROM users WHERE plan <> 'owner' GROUP BY 1 ORDER BY 1""").fetchall()
        return {**f, **act, "mrr": round(float(f["paying_now"]) * PRICE, 2), "price": PRICE,
                "signups_by_day": by_day, "by_track": by_track, "by_level": by_level}
