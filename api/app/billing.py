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


def _start_date(user) -> dict:
    """Se já há acesso pago (ex.: Pix), o cartão só começa a cobrar quando ele terminar."""
    paid = user.get("paid_until")
    if user.get("plan") in ("active", "canceled") and paid is not None:
        if paid > datetime.now(timezone.utc) + timedelta(days=1):
            return {"start_date": paid.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    return {}


def create(user, payer_email: str) -> dict:
    return _call("POST", "/preapproval", {
        "reason": "MeuInglês · assinatura mensal",
        "external_reference": str(user["id"]),
        "payer_email": payer_email,
        "auto_recurring": {"frequency": 1, "frequency_type": "months",
                           "transaction_amount": PRICE, "currency_id": "BRL", **_start_date(user)},
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
        cur = user.get("paid_until")
        if cur and old_plan in ("active", "canceled") and cur > paid_until:
            paid_until = cur  # não encurta acesso já pago (ex.: Pix) ao assinar no cartão
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


# ---------- Pix avulso (30 dias de acesso, sem renovação automática) ----------
PIX_DAYS = 30
PIX_REF = "meuingles:pix:"
BRT = timezone(timedelta(hours=-3))


def _pix_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS pix_payments (
        payment_id text PRIMARY KEY,
        user_id text NOT NULL,
        amount numeric(10,2),
        credited_at timestamptz NOT NULL DEFAULT now())""")


def _post_idem(path: str, body: dict, key: str) -> dict:
    req = urllib.request.Request(API + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + os.environ["MP_ACCESS_TOKEN"],
                                          "Content-Type": "application/json", "X-Idempotency-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        log.warning("Mercado Pago POST %s -> %s %s", path, e.code, detail)
        raise RuntimeError(f"Mercado Pago respondeu {e.code}: {detail}") from None


def pix_create(user) -> dict:
    """Cria um Pix de PRICE no Mercado Pago e devolve o QR Code e o copia e cola."""
    import uuid
    exp = (datetime.now(BRT) + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
    pay = _post_idem("/v1/payments", {
        "transaction_amount": PRICE,
        "description": "MeuInglês · 30 dias de acesso (Pix)",
        "payment_method_id": "pix",
        "payer": {"email": user["email"]},
        "external_reference": PIX_REF + str(user["id"]),
        "notification_url": mailer.base_url() + "api/billing/webhook",
        "date_of_expiration": exp,
    }, str(uuid.uuid4()))
    td = (pay.get("point_of_interaction") or {}).get("transaction_data") or {}
    if not td.get("qr_code"):
        raise RuntimeError("Mercado Pago não devolveu o QR Code do Pix")
    return {"payment_id": str(pay["id"]), "qr_code": td["qr_code"],
            "qr_base64": td.get("qr_code_base64"), "expires": exp, "amount": PRICE}


def pix_confirm(db, payment_id: str, only_user: str | None = None) -> dict:
    """Lê o pagamento na API do Mercado Pago e, se aprovado, soma 30 dias (uma única vez por pagamento)."""
    payment_id = str(payment_id or "")
    if not payment_id.isdigit():
        return {"status": None}
    pay = _call("GET", "/v1/payments/" + payment_id)
    ref = str(pay.get("external_reference") or "")
    if not ref.startswith(PIX_REF):
        return {"status": None}
    uid = ref[len(PIX_REF):]
    if only_user is not None and uid != only_user:
        return {"status": None}
    status = pay.get("status")
    if status != "approved":
        return {"status": status}
    if pay.get("payment_method_id") != "pix" or abs(float(pay.get("transaction_amount") or 0) - PRICE) > 0.01:
        return {"status": "invalid"}
    credited = False
    new_until = None
    user = None
    with db() as conn:
        _pix_table(conn)
        user = conn.execute("SELECT * FROM users WHERE id::text = %s", (uid,)).fetchone()
        if not user or user["plan"] == "owner":
            return {"status": status}
        ins = conn.execute("""INSERT INTO pix_payments (payment_id, user_id, amount) VALUES (%s, %s, %s)
                              ON CONFLICT (payment_id) DO NOTHING RETURNING payment_id""",
                           (payment_id, uid, PRICE)).fetchone()
        if ins:
            now = datetime.now(timezone.utc)
            base = now
            paid = user.get("paid_until")
            if user["plan"] in ("active", "canceled") and paid and paid > base:
                base = paid
            ends = user.get("trial_ends_at")
            if user["plan"] == "trial" and ends and ends > base:
                base = ends
            new_until = base + timedelta(days=PIX_DAYS)
            conn.execute("""UPDATE users SET plan = 'active', paid_until = %s,
                            sub_started_at = coalesce(sub_started_at, now()) WHERE id = %s""",
                         (new_until, user["id"]))
            credited = True
    if credited:
        try:
            until_txt = new_until.astimezone(BRT).strftime("%d/%m/%Y")
            mailer.send(user["email"], "Pagamento por Pix confirmado", [
                f"Oi, {user['name'].split(' ')[0]}! Recebemos seu Pix e seu acesso ao MeuInglês está liberado até {until_txt}.",
                "O Pix não renova sozinho. Quando quiser continuar, é só pagar outro Pix ou assinar no cartão, dentro do app."],
                ("Treinar agora", mailer.base_url() + "app/"))
        except Exception as e:  # noqa: BLE001
            log.warning("E-mail de confirmação do Pix falhou: %s", e)
    return {"status": "approved", "credited": credited, "paid_until": new_until.isoformat() if new_until else None}
