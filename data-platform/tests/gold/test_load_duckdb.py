import pytest

pytest.importorskip("duckdb")
pytest.importorskip("deltalake")

import duckdb  # noqa: E402
import pyarrow as pa  # noqa: E402
from deltalake import write_deltalake  # noqa: E402

from lake import load_duckdb  # noqa: E402


def test_carrega_todas_as_tabelas(tmp_path):
    for t in load_duckdb.TABLES:
        write_deltalake(str(tmp_path / "silver" / t), pa.table({"x": [1, 2, 3]}))
    db = str(tmp_path / "out" / "m.duckdb")
    assert load_duckdb.load(str(tmp_path / "silver"), db) == {t: 3 for t in load_duckdb.TABLES}
    con = duckdb.connect(db, read_only=True)
    try:
        assert con.execute("select count(*) from silver.attempts").fetchone()[0] == 3
    finally:
        con.close()


def test_tabela_ausente_falha(tmp_path):
    write_deltalake(str(tmp_path / "silver" / "attempts"), pa.table({"x": [1]}))
    with pytest.raises(FileNotFoundError):
        load_duckdb.load(str(tmp_path / "silver"), str(tmp_path / "m.duckdb"))
