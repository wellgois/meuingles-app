"""Custo por usuário: áudio avaliado (Azure) + correções com IA (Claude), por situação da conta."""
import os

from fastapi import Depends, HTTPException

PRICE_BRL = float(os.environ.get("PLAN_PRICE", "29.90"))
USD_BRL = float(os.environ.get("USD_BRL", "5.50"))
FEE_PCT = float(os.environ.get("PAY_FEE_PCT", "5"))
AZURE_USD_H = float(os.environ.get("AZURE_USD_PER_HOUR", "1.32"))
LLM_IN = float(os.environ.get("LLM_USD_IN_PER_M", "1.0"))
LLM_OUT = float(os.environ.get("LLM_USD_OUT_PER_M", "5.0"))
DEF_IN = int(os.environ.get("LLM_DEFAULT_IN_TOKENS", "800"))
DEF_OUT = int(os.environ.get("LLM_DEFAULT_OUT_TOKENS", "500"))
TRIAL_MIN = int(os.environ.get("TRIAL_AUDIO_MIN", "120"))
MONTHLY_MIN = int(os.environ.get("MONTHLY_AUDIO_MIN", "300"))

SQL = """
WITH a AS (
  SELECT user_id, count(*) AS attempts,
         coalesce(sum(audio_ms) FILTER (WHERE engine = 'azure'), 0) / 3600000.0 AS az_h,
         count(*) FILTER (WHERE used_llm) AS llm_calls,
         count(*) FILTER (WHERE used_llm AND raw->'result'->'llm'->'usage' IS NOT NULL) AS llm_measured,
         coalesce(sum(CASE WHEN used_llm THEN coalesce((raw->'result'->'llm'->'usage'->>'in')::numeric, %(d_in)s) END), 0) AS tok_in,
         coalesce(sum(CASE WHEN used_llm THEN coalesce((raw->'result'->'llm'->'usage'->>'out')::numeric, %(d_out)s) END), 0) AS tok_out
  FROM attempts WHERE created_at >= date_trunc('month', now()) GROUP BY user_id)
SELECT u.name, u.plan,
       (u.plan IN ('active', 'canceled') OR u.paid_until IS NOT NULL) AS converted,
       CASE WHEN u.plan IN ('active', 'canceled') AND u.paid_until > now() THEN 'paying'
            WHEN u.plan IN ('active', 'canceled') THEN 'churned'
            WHEN u.plan = 'trial' AND (u.trial_ends_at IS NULL OR u.trial_ends_at > now()) THEN 'trial'
            ELSE 'expired' END AS segment,
       a.attempts, a.az_h, a.llm_calls, a.llm_measured, a.tok_in, a.tok_out
FROM a JOIN users u ON u.id = a.user_id
WHERE u.plan <> 'owner'
"""


def _cost(r):
    az = float(r["az_h"]) * AZURE_USD_H
    llm = (float(r["tok_in"]) * LLM_IN + float(r["tok_out"]) * LLM_OUT) / 1e6
    return az, llm


def register(app, db, current_user):
    def admin_only(user=Depends(current_user)):
        if not user["is_admin"]:
            raise HTTPException(403, "Acesso restrito.")
        return user

    @app.get("/api/admin/costs")
    def admin_costs(user=Depends(admin_only)):
        with db() as conn:
            rows = conn.execute(SQL, {"d_in": DEF_IN, "d_out": DEF_OUT}).fetchall()
            paying_now = conn.execute(
                "SELECT count(*) AS n FROM users WHERE plan IN ('active', 'canceled') AND paid_until > now()").fetchone()["n"]
            month = conn.execute("SELECT to_char(date_trunc('month', now()), 'MM/YYYY') AS m").fetchone()["m"]
        brl = lambda usd: round(usd * USD_BRL, 2)
        segs, top = {}, []
        az_t = llm_t = az_h = unconv = 0.0
        calls = measured = 0
        for r in rows:
            az, llm = _cost(r)
            az_t += az
            llm_t += llm
            az_h += float(r["az_h"])
            calls += int(r["llm_calls"])
            measured += int(r["llm_measured"])
            if not r["converted"]:
                unconv += az + llm
            s = segs.setdefault(r["segment"], {"seg": r["segment"], "users": 0, "az": 0.0, "llm": 0.0})
            s["users"] += 1
            s["az"] += az
            s["llm"] += llm
            top.append({"name": r["name"], "seg": r["segment"], "azure_min": round(float(r["az_h"]) * 60, 1),
                        "llm_calls": int(r["llm_calls"]), "usd": az + llm})
        top.sort(key=lambda x: x["usd"], reverse=True)
        top = [{**t, "brl": brl(t["usd"]), "usd": round(t["usd"], 2)} for t in top[:10]]
        order = {"paying": 0, "trial": 1, "expired": 2, "churned": 3}
        segments = [{"seg": s["seg"], "users": s["users"], "azure_brl": brl(s["az"]), "llm_brl": brl(s["llm"]),
                     "total_brl": brl(s["az"] + s["llm"])} for s in sorted(segs.values(), key=lambda x: order.get(x["seg"], 9))]
        p = segs.get("paying", {"az": 0.0, "llm": 0.0})
        paying_cost = brl(p["az"] + p["llm"])
        net_user = PRICE_BRL * (1 - FEE_PCT / 100)
        net = paying_now * net_user
        margin = net - paying_cost
        total = az_t + llm_t
        n = len(rows)
        cap_pay = MONTHLY_MIN / 60 * AZURE_USD_H * USD_BRL
        cap_trial = TRIAL_MIN / 60 * AZURE_USD_H * USD_BRL
        return {
            "month": month,
            "rates": {"azure_h": AZURE_USD_H, "llm_in": LLM_IN, "llm_out": LLM_OUT, "usd_brl": USD_BRL, "fee_pct": FEE_PCT},
            "totals": {"total_usd": round(total, 2), "total_brl": brl(total), "azure_brl": brl(az_t), "llm_brl": brl(llm_t),
                       "azure_h": round(az_h, 4), "llm_calls": calls, "active_users": n,
                       "avg_brl": brl(total / n) if n else 0,
                       "measured_pct": round(100 * measured / calls) if calls else None},
            "paying": {"users": paying_now, "net_per_user_brl": round(net_user, 2), "net_brl": round(net, 2),
                       "cost_brl": paying_cost, "margin_brl": round(margin, 2),
                       "margin_pct": round(100 * margin / net, 1) if net > 0 else None},
            "unconverted_brl": brl(unconv),
            "caps": {"paying_brl": round(cap_pay, 2), "trial_brl": round(cap_trial, 2),
                     "paying_pct_net": round(100 * cap_pay / net_user) if net_user else None},
            "segments": segments, "top": top}
