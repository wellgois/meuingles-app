# MeuInglês

[![CI](https://github.com/wellgois/meuingles-app/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wellgois/meuingles-app/actions/workflows/ci.yml)

[Português](README.pt-BR.md)

Spoken-English trainer for data professionals preparing for job interviews in Brazil. Live at https://meuingles.wellgois.com (landing at `/`, app at `/app/`). The product UI is in Brazilian Portuguese; this documentation is in English.

Early-stage product with a small user base.

## What it does

| Level | What you practice |
|---|---|
| 1 Sounds & Words | Words recorded in the browser and scored per phoneme by Azure Speech |
| 2 Sentences | Same, for full sentences |
| 3 Explain it | Spoken explanations; Claude corrects grammar and rewrites the answer in natural English |
| 4 Your projects (STAR) | Behavioral questions answered by voice, with AI feedback; career tracks choose which questions come first |
| 5 Interview | Mock interview simulator (below) |

Levels 3 and 4 use browser speech recognition, so they keep working when the monthly scored-audio quota runs out.

## Interview simulator (level 5)

- 3 questions: behavioral (STAR), technical and system design, each with one AI follow-up on the weakest part of the answer.
- Report with an overall score and 5 criteria: STAR structure, technical correctness, vocabulary, grammar and clarity. Passing score is 75; the level asks for 2 passed simulations.
- The report is built from the text transcript only. It makes no claims about pronunciation or audio quality.
- Questions come from a fixed bank (level 4 content, 12 technical and 8 system design questions in `api/app/interview.py`), picked at random. They are not generated from the resume.
- Optional "AI suggestion": a draft answer written only from the candidate's resume profile. Answers close to the draft are flagged as assisted, and vocabulary, grammar and clarity scores are capped at 70 for them.
- Answers are deleted when the simulation ends; only the report is kept.

## Resume

PDF, DOCX or pasted text becomes an English profile. The user reviews and edits it before saving. It is stored encrypted at application level, only after explicit consent, and can be downloaded, replaced, deleted or have its consent withdrawn.

## Architecture

```
Browser (PWA, vanilla JS) -> Nginx -> FastAPI (Docker) -> PostgreSQL
                                          |-> Claude Haiku 4.5 (feedback, simulator, resume profile)
                                          |-> Azure Speech (pronunciation, levels 1-2)
                                          |-> Mercado Pago (card subscription, 30-day Pix)
PostgreSQL -> data-platform (pseudonymized extract, lake, dbt)
```

Code layout: `api/app/` (FastAPI), `web/` (landing and app), `ops/` (encrypted backups, restore test), `data-platform/` (pipeline).

## Engineering

- **CI (GitHub Actions):** ruff lint, JS syntax check, schema applied twice against Postgres 16 (must be idempotent), API and extractor tests with pytest, Docker builds, plus Spark/Delta (lake), dbt on DuckDB (gold) and Airflow DAG tests.
- **Deploy:** runs only after every CI job passes. The SSH key can only execute one script, which refuses a dirty working tree, merges fast-forward only, health-checks the API and rolls back to the previous commit if the check fails.
- **Database:** schema changes are additive (`ADD COLUMN IF NOT EXISTS`), so reverting code is safe. Daily encrypted backups with a restore-test script.

## Data platform

The pipeline downstream of this database (pseudonymized extract, ADLS Gen2 landing, Delta bronze/silver, dbt gold, public panel) is documented in [`data-platform/`](data-platform/README.md), including which parts are not provisioned yet.

## Run

```bash
cp .env.example .env   # fill in the values; never commit .env
docker compose up -d --build
curl http://127.0.0.1:$APP_PORT/api/health
```

Tests (need a Postgres database, as in CI):

```bash
cd api && pip install -r requirements.txt -r requirements-dev.txt
DATABASE_URL=postgresql://user:pass@localhost:5432/db pytest -q
```

API docs: `/api/docs`.

## Known limitations

- Pix is a one-off 30-day payment and does not renew by itself.
- The question bank is fixed and only adjusted by career track.
- Simulator speech recognition depends on browser support (Chrome works best); users can type instead.
- No teacher or institution dashboard.
- Scores are produced by an LLM from transcripts. They are practice feedback, not a certification and not a hiring predictor.
