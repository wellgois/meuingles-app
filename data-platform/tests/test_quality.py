import pyarrow as pa

from extractor import quality

K = "a" * 32


def attempts(**over):
    base = {"attempt_id": [1, 2], "user_key": [K, K], "level": [1, 2], "engine": ["azure", "browser"],
            "main_score": [80.0, 70.5], "accuracy": [None, 90.0], "completeness": [None, None], "fluency": [None, None]}
    base.update(over)
    return pa.table(base)


def has(fails, text):
    return any(text in f for f in fails)


def test_dados_validos_passam():
    assert quality.check_tables({"attempts": attempts()}) == []


def test_nota_fora_do_intervalo():
    assert has(quality.check_tables({"attempts": attempts(main_score=[101.0, 70.0])}), "main_score")


def test_email_e_detectado():
    t = pa.table({"pageview_key": [K], "path": ["/contato?a=x@y.com"]})
    assert has(quality.check_tables({"visits": t}), "e-mail")


def test_uuid_cru_em_coluna_comum():
    t = pa.table({"item_id": ["123e4567-e89b-12d3-a456-426614174000"]})
    assert has(quality.check_tables({"x": t}), "UUID")


def test_pseudonimo_fora_do_formato():
    t = attempts(user_key=["123e4567-e89b-12d3-a456-426614174000", K])
    assert has(quality.check_tables({"attempts": t}), "pseudônimo")


def test_tentativa_duplicada():
    assert has(quality.check_tables({"attempts": attempts(attempt_id=[1, 1])}), "duplicada")


def test_palavra_sem_tentativa():
    words = pa.table({"attempt_id": [3], "seq": [0], "score": [50.0]})
    assert has(quality.check_tables({"attempts": attempts(), "attempt_words": words}), "sem tentativa")
