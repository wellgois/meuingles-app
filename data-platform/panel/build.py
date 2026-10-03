"""Painel público da evolução: HTML estático, sem JavaScript, gerado com DuckDB a partir dos Parquet do extrator.
Só entram os dados da conta do dono. Nenhum identificador, texto livre ou dado de outros usuários vai para a página."""
import argparse
import datetime as dt
import glob
import html
import json
import os
import re
from zoneinfo import ZoneInfo

import duckdb

TZ = ZoneInfo("America/Sao_Paulo")
MIN_PHONEME_TRIES = 5
MIN_WORD_TRIES = 3
TOP_N = 8
KEY_RE = re.compile(r"^[0-9a-f]{32}$")

CSS = """
:root{--bg:#f4f7f6;--card:#fff;--text:#0f2a2e;--muted:#52666a;--line:#dfe7e6;--accent:#0e7c86;--goal:#2e7d32}
@media (prefers-color-scheme:dark){:root{--bg:#0d1b1e;--card:#132a2e;--text:#e8f1f0;--muted:#9db4b7;--line:#254046;--accent:#4fd1c5;--goal:#7ad28c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.7rem;line-height:1.2;margin:0 0 4px}
h2{font-size:1.1rem;margin:0 0 8px}
.sub,.note,footer{color:var(--muted);font-size:.9rem}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:16px 0}
section.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;background:none;border:0;padding:0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px}
.kpi strong{display:block;font-size:1.5rem}
.kpi span{color:var(--muted);font-size:.85rem}
.chart{width:100%;height:auto;display:block}
.chart text{fill:var(--muted);font-size:12px}
.grid{stroke:var(--line);stroke-width:1}
.goal{stroke:var(--goal);stroke-width:1.5;stroke-dasharray:5 4}
.line{fill:none;stroke:var(--accent);stroke-width:2.5;stroke-linejoin:round}
.dot{fill:var(--accent)}
.bar{fill:var(--accent);opacity:.85}
.chart text.ipa{font-size:15px;fill:var(--text)}
table{width:100%;border-collapse:collapse;font-size:.95rem}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
.num{text-align:right;font-variant-numeric:tabular-nums}
a{color:var(--accent)}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def fmt(value, digits=1):
    return f"{value:.{digits}f}".replace(".", ",")


def dm(day):
    return day.strftime("%d/%m")


def _pattern(data, table):
    return os.path.join(data, table, "*", "part-0.parquet")


def _exists(data, table):
    return bool(glob.glob(_pattern(data, table)))


def _view(con, data, table):
    pattern = _pattern(data, table).replace("'", "''")
    con.execute(f"create or replace view {table} as select * from "
                f"read_parquet('{pattern}', hive_partitioning=true, union_by_name=true)")


def collect(data, since=None, owner_name="", now=None):
    now = now or dt.datetime.now(TZ)
    stats = {"owner_name": owner_name, "generated_at": now, "since": since, "level": None,
             "total_attempts": 0, "days_practiced": 0, "minutes": 0.0, "avg_all": None, "avg_last7": None,
             "daily": [], "phonemes": [], "words": [], "empty": True}
    if not (_exists(data, "users") and _exists(data, "attempts")):
        return stats
    con = duckdb.connect(":memory:")
    try:
        for table in ("users", "attempts", "attempt_words", "attempt_phonemes"):
            if _exists(data, table):
                _view(con, data, table)
        row = con.execute("select user_key, level from users where is_owner and "
                          "snapshot = (select max(snapshot) from users where is_owner) limit 1").fetchone()
        if not row or not KEY_RE.match(str(row[0])):
            return stats
        key, level = row
        stats["level"] = level
        since_sql = f"and cast(dt as date) >= date '{since.isoformat()}'" if since else ""
        con.execute("create or replace temp view my_attempts as select attempt_id, cast(dt as date) as day, "
                    f"main_score, coalesce(audio_ms, 0) as audio_ms from attempts where user_key = '{key}' "
                    f"and level in (1, 2) {since_sql}")
        daily = [{"day": r[0], "n": int(r[1]), "avg": float(r[2] or 0.0), "minutes": float(r[3] or 0.0)}
                 for r in con.execute("select day, count(*), round(avg(main_score), 1), "
                                      "round(sum(audio_ms) / 60000.0, 2) from my_attempts "
                                      "group by day order by day").fetchall()]
        if not daily:
            return stats
        total, minutes, avg_all, avg7 = con.execute(
            "select count(*), round(sum(audio_ms) / 60000.0, 2), round(avg(main_score), 1), "
            "(select round(avg(main_score), 1) from my_attempts "
            " where day >= (select max(day) from my_attempts) - 6) from my_attempts").fetchone()
        stats.update(daily=daily, total_attempts=int(total), days_practiced=len(daily),
                     minutes=float(minutes or 0.0), avg_all=avg_all, avg_last7=avg7, empty=False)
        if _exists(data, "attempt_phonemes"):
            stats["phonemes"] = [
                {"phoneme": str(r[0]), "n": int(r[1]), "avg": float(r[2])}
                for r in con.execute(
                    "select p.phoneme, count(*), round(avg(p.score), 1) from attempt_phonemes p "
                    "join my_attempts a on a.attempt_id = p.attempt_id "
                    "where p.score is not null and p.phoneme is not null "
                    f"group by p.phoneme having count(*) >= {MIN_PHONEME_TRIES} "
                    f"order by avg(p.score) asc, count(*) desc limit {TOP_N}").fetchall()]
        if _exists(data, "attempt_words"):
            stats["words"] = [
                {"word": str(r[0]), "n": int(r[1]), "pct_ok": int(r[2]), "avg": None if r[3] is None else float(r[3])}
                for r in con.execute(
                    "select w.expected, count(*), "
                    "round(100.0 * sum(case when w.status = 'ok' then 1 else 0 end) / count(*), 0), "
                    "round(avg(w.score), 1) from attempt_words w "
                    "join my_attempts a on a.attempt_id = w.attempt_id where w.expected is not null "
                    f"group by w.expected having count(*) >= {MIN_WORD_TRIES} "
                    f"order by avg(w.score) asc nulls last, count(*) desc limit {TOP_N}").fetchall()]
        return stats
    finally:
        con.close()


def _ticks(d0, d1):
    span = (d1 - d0).days
    if span == 0:
        return [d0]
    seen, out = set(), []
    for f in (0, 0.25, 0.5, 0.75, 1):
        d = d0 + dt.timedelta(days=round(span * f))
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def line_chart(daily):
    w, h = 720, 260
    left, right, top, bottom = 44, 16, 14, 34
    pw, ph = w - left - right, h - top - bottom
    d0, d1 = daily[0]["day"], daily[-1]["day"]
    span = (d1 - d0).days

    def x(day):
        return left + (pw / 2 if span == 0 else (day - d0).days / span * pw)

    def y(value):
        return top + ph - max(0.0, min(100.0, value)) / 100.0 * ph

    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Nota média por dia de treino">']
    for g in (0, 25, 50, 75, 100):
        out.append(f'<line class="grid" x1="{left}" x2="{w - right}" y1="{y(g):.1f}" y2="{y(g):.1f}"/>')
        out.append(f'<text x="{left - 8}" y="{y(g) + 4:.1f}" text-anchor="end">{g}</text>')
    out.append(f'<line class="goal" x1="{left}" x2="{w - right}" y1="{y(80):.1f}" y2="{y(80):.1f}"/>')
    out.append(f'<text x="{w - right}" y="{y(80) - 6:.1f}" text-anchor="end">meta 80</text>')
    if len(daily) > 1:
        pts = " ".join(f"{x(d['day']):.1f},{y(d['avg']):.1f}" for d in daily)
        out.append(f'<polyline class="line" points="{pts}"/>')
    for d in daily:
        tip = f"{dm(d['day'])}: nota média {fmt(d['avg'])} em {d['n']} tentativa(s)"
        out.append(f'<circle class="dot" cx="{x(d["day"]):.1f}" cy="{y(d["avg"]):.1f}" r="4"><title>{esc(tip)}</title></circle>')
    for day in _ticks(d0, d1):
        out.append(f'<text x="{x(day):.1f}" y="{h - 10}" text-anchor="middle">{dm(day)}</text>')
    out.append("</svg>")
    return "".join(out)


def minutes_chart(daily):
    w, h = 720, 200
    left, right, top, bottom = 44, 16, 12, 30
    pw, ph = w - left - right, h - top - bottom
    d0, d1 = daily[0]["day"], daily[-1]["day"]
    span = (d1 - d0).days
    peak = max(d["minutes"] for d in daily) or 1.0
    bw = max(4.0, min(26.0, pw / (span + 1) * 0.7))

    def x(day):
        return left + (pw / 2 if span == 0 else (day - d0).days / span * pw)

    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Minutos de áudio avaliado por dia">']
    for g in (0.0, peak / 2, peak):
        gy = top + ph - g / peak * ph
        out.append(f'<line class="grid" x1="{left}" x2="{w - right}" y1="{gy:.1f}" y2="{gy:.1f}"/>')
        out.append(f'<text x="{left - 8}" y="{gy + 4:.1f}" text-anchor="end">{fmt(g)}</text>')
    for d in daily:
        bh = d["minutes"] / peak * ph
        tip = f"{dm(d['day'])}: {fmt(d['minutes'])} min de áudio avaliado"
        out.append(f'<rect class="bar" x="{x(d["day"]) - bw / 2:.1f}" y="{top + ph - bh:.1f}" '
                   f'width="{bw:.1f}" height="{bh:.1f}" rx="2"><title>{esc(tip)}</title></rect>')
    for day in _ticks(d0, d1):
        out.append(f'<text x="{x(day):.1f}" y="{h - 8}" text-anchor="middle">{dm(day)}</text>')
    out.append("</svg>")
    return "".join(out)


def phoneme_chart(rows):
    row_h, label_w, bar_w = 30, 70, 440
    w, h = label_w + bar_w + 150, row_h * len(rows) + 28
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Sons com pior nota média">']
    goal_x = label_w + 0.8 * bar_w
    out.append(f'<line class="goal" x1="{goal_x:.1f}" x2="{goal_x:.1f}" y1="4" y2="{row_h * len(rows) + 8}"/>')
    out.append(f'<text x="{goal_x:.1f}" y="{h - 6}" text-anchor="middle">80</text>')
    for i, r in enumerate(rows):
        y0 = 8 + i * row_h
        bar = max(0.0, min(100.0, r["avg"])) / 100.0 * bar_w
        out.append(f'<text class="ipa" x="{label_w - 10}" y="{y0 + 17}" text-anchor="end">{esc(r["phoneme"])}</text>')
        out.append(f'<rect class="bar" x="{label_w}" y="{y0 + 3}" width="{bar:.1f}" height="{row_h - 12}" rx="3"/>')
        out.append(f'<text x="{label_w + bar_w + 10}" y="{y0 + 17}">{fmt(r["avg"])} · {r["n"]} tent.</text>')
    out.append("</svg>")
    return "".join(out)


def words_table(rows):
    body = "".join(
        f'<tr><td>{esc(r["word"])}</td><td class="num">{r["n"]}</td><td class="num">{r["pct_ok"]}%</td>'
        f'<td class="num">{"–" if r["avg"] is None else fmt(r["avg"])}</td></tr>' for r in rows)
    return ('<table><thead><tr><th>Palavra</th><th class="num">Tentativas</th><th class="num">Acertos</th>'
            f'<th class="num">Nota média</th></tr></thead><tbody>{body}</tbody></table>')


def kpi(value, label):
    return f'<div class="kpi"><strong>{esc(value)}</strong><span>{esc(label)}</span></div>'


def render(stats):
    when = stats["generated_at"].strftime("%d/%m/%Y %H:%M")
    who = f"{esc(stats['owner_name'])} · " if stats["owner_name"] else ""
    head = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Minha evolução no inglês técnico · MeuInglês</title>'
            '<meta name="description" content="Painel público da minha evolução no inglês falado para engenharia de dados, gerado todo dia pelo pipeline de dados do MeuInglês.">'
            '<meta property="og:title" content="Minha evolução no inglês técnico">'
            '<meta property="og:description" content="Notas, minutos e sons mais difíceis, gerados todo dia por um pipeline de dados.">'
            '<meta property="og:type" content="website">'
            f"<style>{CSS}</style></head><body><main>"
            f'<header><h1>Minha evolução no inglês técnico</h1><p class="sub">{who}atualizado em {when} (Brasília)</p></header>')
    foot = ('<footer><p>Esta página é gerada todo dia pelo pipeline de dados do MeuInglês: Postgres, Parquet '
            'pseudonimizado, DuckDB e HTML estático, sem JavaScript e sem rastreadores. Mostra só os meus dados.</p>'
            '<p><a href="https://meuingles.wellgois.com/">Conheça o MeuInglês</a> · '
            '<a href="https://github.com/wellgois/meuingles-app">Código aberto no GitHub</a></p></footer>'
            "</main></body></html>")
    if stats["empty"]:
        return (head + '<section><h2>Ainda não há treinos registrados no período</h2>'
                '<p class="note">Assim que houver treinos, os gráficos aparecem aqui.</p></section>' + foot)
    daily = stats["daily"]
    since = stats["since"] or daily[0]["day"]
    cards = []
    if stats["level"] is not None:
        cards.append(kpi(stats["level"], "nível atual (de 5)"))
    cards += [kpi(stats["days_practiced"], "dias de treino"), kpi(stats["total_attempts"], "tentativas"),
              kpi(fmt(stats["minutes"]), "min de áudio avaliado"),
              kpi(fmt(stats["avg_last7"]) if stats["avg_last7"] is not None else "–", "nota média, últimos 7 dias"),
              kpi(fmt(stats["avg_all"]) if stats["avg_all"] is not None else "–", "nota média geral")]
    body = [f'<section class="kpis">{"".join(cards)}</section>',
            '<section><h2>Nota média por dia</h2>' + line_chart(daily) +
            f'<p class="note">Desde {since.strftime("%d/%m/%Y")}. Níveis 1 e 2 (palavras e frases). A nota vai de 0 a 100 e mede a pronúncia, avaliada pelo Azure Speech. '
            'A linha pontilhada é a meta de 80, '
            'que vale 5 tentativas seguidas para subir de nível.</p></section>',
            '<section><h2>Minutos de áudio avaliado por dia</h2>' + minutes_chart(daily) + "</section>"]
    if stats["phonemes"]:
        body.append('<section><h2>Sons que mais derrubam a minha nota</h2>' + phoneme_chart(stats["phonemes"]) +
                    f'<p class="note">Nota média por fonema (símbolos IPA). Só entram sons com pelo menos {MIN_PHONEME_TRIES} tentativas.</p></section>')
    if stats["words"]:
        body.append('<section><h2>Palavras mais difíceis</h2>' + words_table(stats["words"]) +
                    f'<p class="note">Exercícios de palavras e frases dos níveis 1 e 2, com pelo menos {MIN_WORD_TRIES} tentativas.</p></section>')
    return head + "".join(body) + foot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="pasta do extrator (tabelas em Parquet)")
    ap.add_argument("--out", required=True, help="arquivo HTML de saída")
    ap.add_argument("--since", help="primeiro dia da série (AAAA-MM-DD); padrão: o configurado ou todo o histórico")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    a = ap.parse_args(argv)
    cfg = {}
    if os.path.exists(a.config):
        with open(a.config, encoding="utf-8") as f:
            cfg = json.load(f)
    raw_since = a.since or cfg.get("since")
    since = dt.date.fromisoformat(raw_since) if raw_since else None
    stats = collect(a.data, since, cfg.get("owner_name", ""))
    page = render(stats)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, a.out)
    summary = {k: stats[k] for k in ("empty", "level", "total_attempts", "days_practiced", "minutes", "avg_all", "avg_last7")}
    summary["phonemes_shown"] = len(stats["phonemes"])
    summary["words_shown"] = len(stats["words"])
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
