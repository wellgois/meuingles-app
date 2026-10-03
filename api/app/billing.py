"""Assinatura mensal pelo Mercado Pago (preapproval sem plano, um por usuário).

O status vem sempre da API do Mercado Pago: o app nunca confia no que chega pelo navegador.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from . import mailer

log = logging.getLogger("meuingles.billing")
API = os.environ.get("MP_API_BASE", "https://api.mercadopago.com")
PRICE = float(os.environ.get("SUB_PRICE", "29.90"))
GRACE = timedelta(days=3)


def configured() -> bool:
    return bool(os.environ.get("MP_ACCESS_TOKEN"))


def _call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + os.environ["MP_ACCESS_TOKEN"],
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        log.warning("Mercado Pago %s %s -> %s %s", method, path, e.code, detail)
        raise RuntimeError(f"Mercado Pago respondeu {e.code}: {detail}") from None


def create(user, payer_email: str) -> dict:
    return _call("POST", "/preapproval", {
        "reason": "MeuInglês · assinatura mensal",
        "external_reference": str(user["id"]),
        "payer_email": payer_email,
        "auto_recurring": {"frequency": 1, "frequency_type": "months",
                           "transaction_amount": PRICE, "currency_id": "BRL"},
        "back_url": mailer.base_url() + "app/?assinatura=1",
        "status": "pending",
    })


def get(preapproval_id: str) -> dict:
    return _call("GET", "/preapproval/" + preapproval_id)


def cancel(preapproval_id: str) -> dict:
    return _call("PUT", "/preapproval/" + preapproval_id, {"status": "cancelled"})


def _date(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def apply(conn, pre: dict) -> str | None:
    """Grava o status de uma assinatura no usuário dono dela. Devolve 'activated', 'cancelled' ou None."""
    uid = pre.get("external_reference")
    user = conn.execute("SELECT * FROM users WHERE id::text = %s", (uid,)).fetchone() if uid else None
    if not user or user["plan"] == "owner":
        return None
    status = pre.get("status")
    now = datetime.now(timezone.utc)
    nxt = _date(pre.get("next_payment_date"))
    old_plan = user["plan"]
    if status == "authorized":
        paid_until = (nxt or now + timedelta(days=31)) + GRACE
        conn.execute("""UPDATE users SET plan = 'active', mp_preapproval_id = %s, mp_status = %s, paid_until = %s,
                        sub_started_at = coalesce(sub_started_at, now()) WHERE id = %s""",
                     (pre["id"], status, paid_until, user["id"]))
        if old_plan != "active":
            mailer.send(user["email"], "Sua assinatura do MeuInglês está ativa", [
                f"Oi, {user['name'].split(' ')[0]}! Recebemos a confirmação do Mercado Pago e sua assinatura está ativa.",
                f"São R$ {PRICE:.2f} por mês".replace(".", ",") + ", com até 300 minutos de pronúncia avaliada. "
                "Você pode cancelar quando quiser, no próprio app."], ("Treinar agora", mailer.base_url() + "app/"))
            return "activated"
    elif status in ("cancelled", "paused"):
        keep = user["paid_until"] if old_plan == "active" else None
        conn.execute("""UPDATE users SET plan = CASE WHEN plan = 'active' THEN 'canceled' ELSE plan END,
                        mp_preapproval_id = %s, mp_status = %s, paid_until = coalesce(%s, paid_until) WHERE id = %s""",
                     (pre["id"], status, keep, user["id"]))
        if old_plan == "active":
            until = (keep or now).astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")
            mailer.send(user["email"], "Sua assinatura do MeuInglês foi cancelada", [
                f"Oi, {user['name'].split(' ')[0]}. Sua assinatura foi cancelada e não haverá novas cobranças.",
                f"Você continua com acesso até {until}. Seu histórico fica salvo se quiser voltar."],
                ("Abrir o MeuInglês", mailer.base_url() + "app/"))
            return "cancelled"
    else:
        conn.execute("UPDATE users SET mp_preapproval_id = %s, mp_status = %s WHERE id = %s",
                     (pre["id"], status, user["id"]))
    return None


def sync_all(db) -> int:
    """Confere no Mercado Pago as assinaturas em andamento (roda a cada hora)."""
    if not configured():
        return 0
    n = 0
    with db() as conn:
        rows = conn.execute("""SELECT mp_preapproval_id FROM users WHERE mp_preapproval_id IS NOT NULL
                               AND (plan IN ('active', 'canceled') OR (mp_status = 'pending'
                                    AND mp_created_at > now() - interval '3 days'))""").fetchall()
    for r in rows:
        try:
            pre = get(r["mp_preapproval_id"])
            with db() as conn:
                if apply(conn, pre):
                    n += 1
        except Exception as e:  # noqa: BLE001 - uma assinatura com erro não para as outras
            log.warning("Falha ao conferir assinatura %s: %s", r["mp_preapproval_id"], e)
    return n
