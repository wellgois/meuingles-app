import datetime as dt
import json
import os

import pytest

pytest.importorskip("duckdb")

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from extractor import tables as T  # noqa: E402
from panel import build  # noqa: E402

TS = dt.datetime(2026, 10, 1, 15, 0, tzinfo=dt.timezone.utc)
OWNER, OTHER = "a" * 32, "b" * 32
SCRIPT_WORD = "<script>alert(1)</script>"


def write(root, table, partition, rows):
    t = pa.Table.from_pylist(rows, schema=pa.schema(T.SPECS[table].schema))
    folder = os.path.join(root, table, partition)
    os.makedirs(folder, exist_ok=True)
    pq.write_table(t, os.path.join(folder, "part-0.parquet"))


def attempt(i, user, score, audio):
    return {"attempt_id": i, "user_key": user, "created_at": TS, "level": 1, "item_id": f"w{i}",
            "engine": "azure", "main_score": score, "audio_ms": audio}


def phoneme(i, seq, ph, score):
    return {"attempt_id": i, "word_seq": 0, "phoneme_seq": seq, "phoneme": ph, "score": score,
            "attempt_created_at": TS}


def word(i, seq, text, status, score):
    return {"attempt_id": i, "seq": seq, "expected": text, "heard": text, "status": status, "score": score,
            "attempt_created_at": TS}


@pytest.fixture()
def data(tmp_path):
    root = str(tmp_path)
    write(root, "users", "snapshot=2026-10-05", [
        {"user_key": OWNER, "level": 3, "plan": "owner", "is_owner": True, "created_at": TS},
        {"user_key": OTHER, "level": 1, "plan": "trial", "is_owner": False, "created_at": TS}])
    write(root, "attempts", "dt=2026-10-01", [attempt(1, OWNER, 60.0, 30000), attempt(2, OWNER, 80.0, 30000)])
    write(root, "attempts", "dt=2026-10-02", [attempt(3, OWNER, 90.0, 60000), attempt(5, OTHER, 10.0, 600000)])
    write(root, "attempts", "dt=2026-10-03", [attempt(4, OWNER, 70.0, 30000)])
    theta = [(1, 40.0), (2, 50.0), (3, 60.0), (4, 50.0), (1, 50.0), (2, 50.0)]
    rows = [phoneme(i, n, "θ", s) for n, (i, s) in enumerate(theta)]
    rows += [phoneme(i, 10 + i, "ɹ", 70.0) for i in (1, 2, 3, 4)]
    rows += [phoneme(5, 20 + n, "ʒ", 10.0) for n in range(10)]
    write(root, "attempt_phonemes", "dt=2026-10-01", rows)
    words = []
    for i, status, score in [(1, "ok", 90.0), (2, "ok", 80.0), (3, "wrong", 30.0)]:
        words += [word(i, 0, "idempotent", status, score), word(i, 1, SCRIPT_WORD, "wrong", 20.0)]
    words += [word(5, n, "secretword", "wrong", 5.0) for n in range(5)]
    write(root, "attempt_words", "dt=2026-10-01", words)
    return root


def test_collect_so_do_dono(data):
    s = build.collect(data)
    assert s["empty"] is False
    assert s["level"] == 3
    assert s["total_attempts"] == 4
    assert s["days_practiced"] == 3
    assert s["minutes"] == pytest.approx(2.5)
    assert s["avg_all"] == pytest.approx(75.0)
    assert s["avg_last7"] == pytest.approx(75.0)
    assert [d["n"] for d in s["daily"]] == [2, 1, 1]
    assert [(p["phoneme"], p["n"], p["avg"]) for p in s["phonemes"]] == [("θ", 6, 50.0)]
    assert [(w["word"], w["n"]) for w in s["words"]] == [(SCRIPT_WORD, 3), ("idempotent", 3)]
    assert [w["pct_ok"] for w in s["words"]] == [0, 67]


def test_collect_desde_uma_data(data):
    s = build.collect(data, since=dt.date(2026, 10, 2))
    assert s["total_attempts"] == 2
    assert s["days_practiced"] == 2


def test_pagina_nao_vaza_nem_executa_nada(data):
    page = build.render(build.collect(data, owner_name="Pessoa Dona"))
    for forbidden in (OWNER, OTHER, "secretword", "ʒ", "ɹ", "<script", "src=", "<link", "<iframe"):
        assert forbidden not in page
    assert "&lt;script&gt;" in page
    assert "θ" in page
    assert "Pessoa Dona" in page


def test_sem_treinos(tmp_path):
    root = str(tmp_path)
    write(root, "users", "snapshot=2026-10-05",
          [{"user_key": OWNER, "level": 1, "plan": "owner", "is_owner": True, "created_at": TS}])
    write(root, "attempts", "dt=2026-10-01", [])
    s = build.collect(root)
    assert s["empty"] is True
    assert "Ainda não há treinos" in build.render(s)


def test_sem_dados(tmp_path):
    s = build.collect(str(tmp_path / "nada"))
    assert s["empty"] is True
    assert "Ainda não há treinos" in build.render(s)


def test_cli_grava_a_pagina_e_resume(data, tmp_path, capsys):
    out = tmp_path / "pub" / "index.html"
    rc = build.main(["--data", data, "--out", str(out), "--config", str(tmp_path / "nao-existe.json")])
    assert rc == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert not (tmp_path / "pub" / "index.html.tmp").exists()
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_attempts"] == 4 and summary["empty"] is False
