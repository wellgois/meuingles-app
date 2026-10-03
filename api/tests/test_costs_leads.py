import re
from pathlib import Path

import pytest

from app import costs, leads

JS = Path(__file__).resolve().parents[2] / "web" / "app.js"


def test_custo_por_conta():
    r = {"az_h": 1, "tok_in": 1_000_000, "tok_out": 1_000_000}
    az, llm = costs._cost(r)
    assert az == pytest.approx(costs.AZURE_USD_H)
    assert llm == pytest.approx(costs.LLM_IN + costs.LLM_OUT)


def test_filtros_validos():
    assert leads.SEGMENTS["all"] == "true"
    assert all(v.startswith("t.") for v in leads.ORDERS.values())


def test_filtros_da_api_batem_com_o_painel():
    js = JS.read_text(encoding="utf-8")
    block = re.search(r"const SEG_LABEL = \{(.*?)\};", js, re.S)
    assert block, "SEG_LABEL não encontrado em web/app.js"
    keys = set(re.findall(r"(\w+):\s*\"", block.group(1)))
    assert keys == set(leads.SEGMENTS)
