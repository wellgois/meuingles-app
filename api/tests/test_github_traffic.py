from datetime import date
from pathlib import Path

from app import github_traffic as gh

JS = Path(__file__).resolve().parents[2] / "web" / "app.js"
HTML = Path(__file__).resolve().parents[2] / "web" / "app" / "index.html"

DATA = {
    "daily": [
        {"date": "2026-10-01", "repo": "a", "views": "9", "unique_views": "1", "clones": "27", "unique_clones": "16"},
        {"date": "2026-10-07", "repo": "a", "views": "5", "unique_views": "3", "clones": "2", "unique_clones": "1"},
        {"date": "2026-10-08", "repo": "b", "views": "2", "unique_views": "2", "clones": "0", "unique_clones": "0"},
    ],
    "referrers": [
        {"snapshot": "2026-10-08", "repo": "a", "referrer": "velho.com", "views": "50", "uniques": "50"},
        {"snapshot": "2026-10-09", "repo": "a", "referrer": "linkedin.com", "views": "4", "uniques": "2"},
        {"snapshot": "2026-10-09", "repo": "b", "referrer": "github.com", "views": "1", "uniques": "1"},
    ],
    "paths": [{"snapshot": "2026-10-09", "repo": "a", "path": "/x/a", "title": "t", "views": "4", "uniques": "2"}],
    "repo_stats": [
        {"date": "2026-09-20", "repo": "a", "stars": "1", "forks": "0", "watchers": "1"},
        {"date": "2026-10-09", "repo": "a", "stars": "4", "forks": "1", "watchers": "1"},
        {"date": "2026-10-09", "repo": "b", "stars": "0", "forks": "0", "watchers": "0"},
    ],
    "stargazers": [
        {"repo": "a", "user": "alice", "starred_at": "2026-10-05T10:00:00Z"},
        {"repo": "a", "user": "bad user<script>", "starred_at": "2026-10-08T10:00:00Z"},
        {"repo": "a", "user": "bob", "starred_at": "2026-10-07T10:00:00Z"},
    ],
}


def test_resumo_da_janela_e_totais():
    r = gh.summarize(DATA, 7, today=date(2026, 10, 9))
    assert r["totals"]["views"] == 7 and r["totals"]["uniques"] == 5  # o dia 01/10 fica fora dos 7 dias
    a = next(x for x in r["repos"] if x["repo"] == "a")
    assert (a["views"], a["uniques"], a["clones"], a["stars"], a["stars_delta"]) == (5, 3, 2, 4, 3)
    assert len(r["by_day"]) == 7 and r["by_day"][-1]["day"] == "2026-10-09"
    r30 = gh.summarize(DATA, 30, today=date(2026, 10, 9))
    assert r30["totals"]["views"] == 16


def test_origens_so_da_foto_mais_recente_e_estrelas_validas():
    r = gh.summarize(DATA, 7, today=date(2026, 10, 9))
    assert [x["referrer"] for x in r["refs"]] == ["linkedin.com", "github.com"]
    assert r["refs_date"] == "2026-10-09"
    assert [s["user"] for s in r["stargazers"]] == ["bob", "alice"]  # login inválido descartado, mais novo primeiro


def test_sem_dados_nao_quebra():
    empty = {k: [] for k in gh.FILES}
    r = gh.summarize(empty, 7, today=date(2026, 10, 9))
    assert r["totals"]["views"] == 0 and r["refs"] == [] and r["totals"]["stars_delta"] is None


def test_painel_do_front_aponta_para_a_api():
    js = JS.read_text(encoding="utf-8")
    assert 'api("admin/github?days="' in js and 'id="admGithub"' in js and "loadGithub()" in js
