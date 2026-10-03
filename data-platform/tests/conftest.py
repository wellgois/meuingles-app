"""Nos jobs da CI que definem FAIL_ON_SKIP, teste ignorado por falta de dependência vira falha (evita falso verde)."""
import os

import pytest


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if not os.environ.get("FAIL_ON_SKIP"):
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter else []
    if skipped and session.exitstatus == 0:
        session.exitstatus = 1
        print(f"\nFAIL_ON_SKIP: {len(skipped)} item(ns) ignorado(s); instale as dependências do job.")
