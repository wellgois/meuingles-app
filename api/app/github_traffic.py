"""Painel de divulgação no GitHub (só administrador).

Lê os CSVs que a rotina diária do repositório privado `github-traffic` grava (visitas, origens, estrelas dos
repositórios públicos) e devolve um resumo. Precisa de GITHUB_TRAFFIC_TOKEN no .env: um token fine-grained
com permissão somente de leitura (Contents: Read-only) apenas nesse repositório.
"""
import csv
import io
import os
import re
import time
import urllib.request
from datetime import date, timedelta

from fastapi import Depends, HTTPException, Query

REPO = os.environ.get("GITHUB_TRAFFIC_REPO", "wellgois/github-traffic")
FILES = ("daily", "referrers", "paths", "repo_stats", "stargazers")
CACHE_S = 600
LOGIN_RE = re.compile(r"^[A-Za-z0-9-]{1,39}$")
_cache = {"at": 0.0, "data": None}


def _token():
    return os.environ.get("GITHUB_TRAFFIC_TOKEN", "").strip()


def _get_csv(name):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/contents/data/{name}.csv",
        headers={"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github.raw+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "meuingles-admin"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def load():
    if _cache["data"] is not None and time.time() - _cache["at"] < CACHE_S:
        return _cache["data"]
    data = {n: _get_csv(n) for n in FILES}
    _cache.update(at=time.time(), data=data)
    return data


def _n(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _latest_snapshot(rows):
    """Origens e páginas vêm em janelas de 14 dias que se sobrepõem: vale só a foto mais recente de cada repositório."""
    newest = {}
    for r in rows:
        newest[r["repo"]] = max(newest.get(r["repo"], ""), r["snapshot"])
    return [r for r in rows if r["snapshot"] == newest[r["repo"]]], max(newest.values(), default="")


def summarize(data, days, today=None):
    today = today or date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    end = today.isoformat()
    repos = sorted({r["repo"] for r in data["daily"]} | {r["repo"] for r in data["repo_stats"]})

    per = {r: {"repo": r, "views": 0, "uniques": 0, "clones": 0, "unique_clones": 0,
               "stars": 0, "forks": 0, "stars_delta": None} for r in repos}
    by_day = {(today - timedelta(days=days - 1 - i)).isoformat(): {"views": 0, "uniques": 0} for i in range(days)}
    for r in data["daily"]:
        if not start <= r["date"] <= end:
            continue
        p = per[r["repo"]]
        p["views"] += _n(r["views"])
        p["uniques"] += _n(r["unique_views"])
        p["clones"] += _n(r["clones"])
        p["unique_clones"] += _n(r["unique_clones"])
        by_day[r["date"]]["views"] += _n(r["views"])
        by_day[r["date"]]["uniques"] += _n(r["unique_views"])

    hist = {}
    for r in sorted(data["repo_stats"], key=lambda x: x["date"]):
        hist.setdefault(r["repo"], []).append(r)
    for repo, rows in hist.items():
        last = rows[-1]
        per[repo]["stars"], per[repo]["forks"] = _n(last["stars"]), _n(last["forks"])
        before = [x for x in rows if x["date"] < start]
        base = before[-1] if before else rows[0]
        if base is not last:
            per[repo]["stars_delta"] = _n(last["stars"]) - _n(base["stars"])

    refs, refs_date = _latest_snapshot(data["referrers"])
    paths, _ = _latest_snapshot(data["paths"])
    refs = sorted(refs, key=lambda r: (-_n(r["uniques"]), -_n(r["views"])))[:12]
    paths = sorted(paths, key=lambda r: (-_n(r["uniques"]), -_n(r["views"])))[:8]
    stars = [s for s in sorted(data["stargazers"], key=lambda s: s["starred_at"], reverse=True)
             if LOGIN_RE.match(s["user"])][:20]

    rows = list(per.values())
    return {
        "configured": True, "days": days, "repos": rows, "refs_date": refs_date,
        "totals": {"views": sum(r["views"] for r in rows), "uniques": sum(r["uniques"] for r in rows),
                   "stars": sum(r["stars"] for r in rows), "forks": sum(r["forks"] for r in rows),
                   "stars_delta": (sum(r["stars_delta"] or 0 for r in rows)
                                   if any(r["stars_delta"] is not None for r in rows) else None)},
        "by_day": [{"day": d, **v} for d, v in sorted(by_day.items())],
        "refs": [{"repo": r["repo"], "referrer": r["referrer"], "views": _n(r["views"]), "uniques": _n(r["uniques"])} for r in refs],
        "paths": [{"repo": r["repo"], "path": r["path"], "views": _n(r["views"]), "uniques": _n(r["uniques"])} for r in paths],
        "stargazers": [{"repo": s["repo"], "user": s["user"], "starred_at": s["starred_at"]} for s in stars],
    }


def register(app, current_user):
    def admin_only(user=Depends(current_user)):
        if not user["is_admin"]:
            raise HTTPException(403, "Acesso restrito.")
        return user

    @app.get("/api/admin/github")
    def admin_github(days: int = Query(7), user=Depends(admin_only)):
        if days not in (7, 30, 90):
            days = 7
        if not _token():
            return {"configured": False}
        try:
            data = load()
        except (OSError, ValueError, KeyError, csv.Error):
            data = _cache["data"]
            if data is None:
                raise HTTPException(502, "Não consegui ler os dados do GitHub. Confira o GITHUB_TRAFFIC_TOKEN e o nome do repositório.")
        try:
            return summarize(data, days)
        except (ValueError, KeyError):
            raise HTTPException(502, "Os arquivos do repositório de tráfego estão num formato inesperado.")
