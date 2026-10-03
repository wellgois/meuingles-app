"""Medição de visitas ao site (sem cookies, sem IP) e painel de tráfego para administradores."""
import re
import uuid

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from . import auth

TZ = "America/Sao_Paulo"
BOT_RE = re.compile(r"bot|crawl|spider|preview|headless|slurp|facebookexternalhit|lighthouse|pingdom|uptime", re.I)
INAPP_OK = {"linkedin", "facebook", "instagram"}

SRC = r"""COALESCE(NULLIF(lower(utm_source), ''),
  CASE WHEN inapp <> '' THEN inapp
       WHEN ref_host ~ '(^|\.)(linkedin\.com|lnkd\.in)$' THEN 'linkedin'
       WHEN ref_host ~ '(^|\.)google\.' THEN 'google'
       WHEN ref_host ~ '(^|\.)(t\.co|twitter\.com|x\.com)$' THEN 'x'
       WHEN ref_host ~ '(^|\.)(facebook\.com|fb\.com|instagram\.com)$' THEN 'meta'
       WHEN ref_host ~ '(whatsapp|wa\.me)' THEN 'whatsapp'
       WHEN ref_host IS NULL OR ref_host = '' THEN 'direto'
       ELSE ref_host END)"""

BASE = f"""WITH v AS (SELECT *, {SRC} AS src FROM visits WHERE created_at > now() - make_interval(days => %s)),
sess AS (SELECT sid, min(vid) AS vid, min(created_at) AS started,
                (array_agg(src ORDER BY created_at))[1] AS src,
                (array_agg(coalesce(utm_campaign, '') ORDER BY created_at))[1] AS campaign,
                (array_agg(coalesce(utm_content, '') ORDER BY created_at))[1] AS content,
                (array_agg(device ORDER BY created_at))[1] AS device,
                count(*) AS pages, sum(dur_s) AS dur, bool_or(clicked_cta) AS cta,
                bool_or(left(path, 4) = '/app') AS app_open
         FROM v GROUP BY sid)
"""


class TrackIn(BaseModel):
    pv: str = Field(max_length=40)
    vid: str = Field(max_length=40)
    sid: str = Field(max_length=40)
    path: str = Field(default="/", max_length=200)
    ref: str = Field(default="", max_length=120)
    us: str = Field(default="", max_length=80)
    um: str = Field(default="", max_length=80)
    uc: str = Field(default="", max_length=80)
    ut: str = Field(default="", max_length=80)
    ia: str = Field(default="", max_length=20)
    w: int = 0
    nw: int = 0
    dur: int = 0
    sc: int = 0
    cta: int = 0


def classify_source(utm, ref, inapp=""):
    utm = (utm or "").strip().lower()[:80]
    if utm:
        return utm
    if inapp in INAPP_OK:
        return inapp
    h = (ref or "").strip().lower()[:120]
    if not h:
        return "direto"
    if re.search(r"(^|\.)(linkedin\.com|lnkd\.in)$", h):
        return "linkedin"
    if re.search(r"(^|\.)google\.", h):
        return "google"
    if re.search(r"(^|\.)(t\.co|twitter\.com|x\.com)$", h):
        return "x"
    if re.search(r"(^|\.)(facebook\.com|fb\.com|instagram\.com)$", h):
        return "meta"
    if re.search(r"(whatsapp|wa\.me)", h):
        return "whatsapp"
    return h


def signup_attribution(body):
    def clean(v):
        return ((v or "").strip().lower()[:80]) or None
    src = classify_source(body.utm_source, body.ref, body.inapp)
    try:
        vid = str(uuid.UUID(body.vid)) if body.vid else None
    except ValueError:
        vid = None
    return src, clean(body.utm_campaign), clean(body.utm_content), vid


def register(app, db, current_user):
    def admin_only(user=Depends(current_user)):
        if not user["is_admin"]:
            raise HTTPException(403, "Acesso restrito.")
        return user

    @app.post("/api/t", status_code=204)
    def track(p: TrackIn, request: Request):
        if BOT_RE.search(request.headers.get("user-agent", "")):
            return Response(status_code=204)
        try:
            pv, vid, sid = (str(uuid.UUID(x)) for x in (p.pv, p.vid, p.sid))
        except ValueError:
            return Response(status_code=204)
        auth.rate_limit("t:" + vid, 400, 3600)
        path = p.path if p.path.startswith("/") else "/" + p.path
        device = "mobile" if p.w and p.w < 768 else "tablet" if p.w and p.w < 1100 else "desktop"
        clean = lambda v: (v or "").strip().lower()[:80] or None
        with db() as conn:
            conn.execute(
                """INSERT INTO visits (pv, vid, sid, path, ref_host, utm_source, utm_medium, utm_campaign, utm_content,
                                       device, inapp, is_new, dur_s, max_scroll, clicked_cta)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (pv) DO UPDATE SET
                       dur_s = GREATEST(visits.dur_s, EXCLUDED.dur_s),
                       max_scroll = GREATEST(visits.max_scroll, EXCLUDED.max_scroll),
                       clicked_cta = visits.clicked_cta OR EXCLUDED.clicked_cta,
                       updated_at = now()
                   WHERE visits.vid = EXCLUDED.vid""",
                (pv, vid, sid, path[:200], clean(p.ref), clean(p.us), clean(p.um), clean(p.uc), clean(p.ut),
                 device, p.ia if p.ia in INAPP_OK else "", bool(p.nw),
                 max(0, min(p.dur, 1800)), max(0, min(p.sc, 100)), bool(p.cta)))
        return Response(status_code=204)

    @app.get("/api/admin/traffic")
    def admin_traffic(days: int = Query(7), user=Depends(admin_only)):
        if days not in (7, 30, 90):
            days = 7
        with db() as conn:
            pv = conn.execute(
                """SELECT count(*) AS pageviews, count(DISTINCT vid) AS visitors,
                          count(DISTINCT vid) FILTER (WHERE is_new) AS new_visitors
                   FROM visits WHERE created_at > now() - make_interval(days => %s)""", (days,)).fetchone()
            t = conn.execute(BASE + """SELECT count(*) AS sessions,
                       count(*) FILTER (WHERE pages = 1 AND dur < 10) AS bounces,
                       round(coalesce(avg(dur), 0)) AS avg_dur,
                       round(coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY dur), 0)) AS med_dur,
                       count(*) FILTER (WHERE cta) AS cta, count(*) FILTER (WHERE app_open) AS app_open
                     FROM sess""", (days,)).fetchone()
            by_source = conn.execute(BASE + """SELECT src AS k, count(DISTINCT vid) AS visitors, count(*) AS sessions,
                       round(coalesce(avg(dur), 0)) AS avg_dur,
                       round(100.0 * count(*) FILTER (WHERE pages = 1 AND dur < 10) / count(*)) AS bounce_pct,
                       count(*) FILTER (WHERE cta) AS cta, count(*) FILTER (WHERE app_open) AS app_open
                     FROM sess GROUP BY src ORDER BY sessions DESC LIMIT 12""", (days,)).fetchall()
            by_campaign = conn.execute(BASE + """SELECT campaign, content, src, count(*) AS sessions,
                       round(coalesce(avg(dur), 0)) AS avg_dur, count(*) FILTER (WHERE cta) AS cta,
                       count(*) FILTER (WHERE app_open) AS app_open
                     FROM sess WHERE campaign <> '' GROUP BY campaign, content, src
                     ORDER BY sessions DESC LIMIT 15""", (days,)).fetchall()
            by_device = conn.execute(BASE + """SELECT device AS k, count(*) AS n FROM sess
                     GROUP BY device ORDER BY n DESC""", (days,)).fetchall()
            by_hour = conn.execute(BASE + f"""SELECT extract(hour FROM started AT TIME ZONE '{TZ}')::int AS h,
                       count(*) AS n FROM sess GROUP BY 1 ORDER BY 1""", (days,)).fetchall()
            by_day = conn.execute(BASE + f"""SELECT to_char(d, 'YYYY-MM-DD') AS day, count(s.sid) AS sessions,
                       count(DISTINCT s.vid) AS visitors
                     FROM generate_series((now() AT TIME ZONE '{TZ}')::date - {days - 1},
                                          (now() AT TIME ZONE '{TZ}')::date, interval '1 day') d
                     LEFT JOIN sess s ON (s.started AT TIME ZONE '{TZ}')::date = d::date
                     GROUP BY d ORDER BY d""", (days,)).fetchall()
            pages = conn.execute(
                """SELECT path, count(*) AS views, round(coalesce(avg(dur_s), 0)) AS avg_dur,
                          round(coalesce(avg(max_scroll), 0)) AS scroll
                   FROM visits WHERE created_at > now() - make_interval(days => %s)
                   GROUP BY path ORDER BY views DESC LIMIT 8""", (days,)).fetchall()
            signups = conn.execute(
                """SELECT count(*) AS n FROM users WHERE plan <> 'owner'
                   AND created_at > now() - make_interval(days => %s)""", (days,)).fetchone()["n"]
            signups_tracked = conn.execute(
                """SELECT count(*) AS n FROM users WHERE plan <> 'owner' AND signup_vid IS NOT NULL
                   AND created_at > now() - make_interval(days => %s)""", (days,)).fetchone()["n"]
            online = conn.execute(
                "SELECT count(DISTINCT vid) AS n FROM visits WHERE updated_at > now() - interval '5 minutes'").fetchone()["n"]
        with db() as conn:
            su_source = conn.execute(
                """SELECT coalesce(signup_source, 'sem origem') AS k, count(*) AS n,
                          count(*) FILTER (WHERE email_verified) AS verified,
                          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM attempts a WHERE a.user_id = users.id)) AS practiced,
                          count(*) FILTER (WHERE plan IN ('active', 'canceled') OR paid_until IS NOT NULL) AS paid
                   FROM users WHERE plan <> 'owner' AND created_at > now() - make_interval(days => %s)
                   GROUP BY 1 ORDER BY n DESC LIMIT 12""", (days,)).fetchall()
            su_campaign = conn.execute(
                """SELECT signup_campaign AS campaign, coalesce(signup_content, '') AS content,
                          coalesce(signup_source, '') AS src, count(*) AS n,
                          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM attempts a WHERE a.user_id = users.id)) AS practiced,
                          count(*) FILTER (WHERE plan IN ('active', 'canceled') OR paid_until IS NOT NULL) AS paid
                   FROM users WHERE plan <> 'owner' AND signup_campaign IS NOT NULL
                        AND created_at > now() - make_interval(days => %s)
                   GROUP BY 1, 2, 3 ORDER BY n DESC LIMIT 15""", (days,)).fetchall()
        return {**pv, **t, "su_source": su_source, "su_campaign": su_campaign, "days": days, "signups": signups, "signups_tracked": signups_tracked, "online": online, "by_source": by_source,
                "by_campaign": by_campaign, "by_device": by_device, "by_hour": by_hour, "by_day": by_day,
                "pages": pages}
