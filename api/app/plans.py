"""Planos do MeuInglês: preço no cartão e no Pix, simulações e minutos de áudio por mês."""

TIERS = {
    "basico":    {"name": "Básico",    "card": 22.90, "pix": 21.90, "sims": 10, "audio_min": 30},
    "pro":       {"name": "Pro",       "card": 29.90, "pix": 27.90, "sims": 20, "audio_min": 60},
    "intensivo": {"name": "Intensivo", "card": 40.90, "pix": 38.90, "sims": 30, "audio_min": 120},
}


def public():
    return [{"id": k, "name": v["name"], "card": v["card"], "pix": v["pix"],
             "sims": v["sims"], "audio_min": v["audio_min"]} for k, v in TIERS.items()]


import os

FEE_CARD = float(os.environ.get("PAY_FEE_CARD_PCT", "4.99"))
FEE_PIX = float(os.environ.get("PAY_FEE_PIX_PCT", "0.99"))
LEGACY = float(os.environ.get("PLAN_PRICE", "29.90"))


def value(tier, mp_status):
    """(receita bruta, receita líquida) mensal de um pagante, pelo plano e pela forma de pagamento."""
    card = mp_status == "authorized"
    t = TIERS.get(tier or "")
    gross = (t["card"] if card else t["pix"]) if t else LEGACY
    fee = FEE_CARD if card else FEE_PIX
    return gross, gross * (1 - fee / 100)
