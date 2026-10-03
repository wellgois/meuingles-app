"""Contrato entre o extrator (landing) e o lake: tabelas e tipo de partição."""

DAILY = ["attempts", "attempt_words", "attempt_phonemes", "visits"]
SNAPSHOT = ["users", "review_items", "deleted_users"]
ALL = DAILY + SNAPSHOT


def partition_col(table: str) -> str:
    return "dt" if table in DAILY else "snapshot"
