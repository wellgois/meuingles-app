"""Card "Simular entrevista CI&T": conteúdo estático, sem banco."""
from app import ciet_card


def test_card_tem_5_perguntas_com_resposta_em_ingles():
    c = ciet_card.card()
    assert c["title"] == "Simular entrevista CI&T"
    assert len(c["items"]) == 5
    ids = [i["id"] for i in c["items"]]
    assert len(set(ids)) == 5
    for it in c["items"]:
        assert it["question"].strip().endswith("?")
        assert 60 <= len(it["answer"].split()) <= 220
        assert it["tag"] and it["notes"]


def test_respostas_nao_prometem_o_que_nao_existe():
    texto = " ".join(i["answer"] for i in ciet_card.ITEMS).lower()
    assert "adls" not in texto
    assert "in production" not in texto
    assert "terraform yet" in texto
