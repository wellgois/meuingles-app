# MeuInglês

A speaking coach for technical English in data engineering. You talk, the app scores what you said word by word, keeps a spaced-repetition notebook of the words you miss, and suggests sentences to practice. It is also the source system of a data platform built with the tools of my data engineering postgraduate course.

Live at `wellgois.com/meuingles`.

## Current status: phase 1 (basic mode)

| Part | Status |
| --- | --- |
| Speech capture | Browser speech recognition (Chrome), no API key needed |
| Scoring | Word alignment between target and transcript (`difflib`), per-word status: ok, close, wrong, missing, extra |
| Levels | 1 Sounds & Words, 2 Sentences, 3 Explain it, 4 Your projects (STAR) |
| Level up | 5 attempts in a row scoring 80 or more |
| Review notebook | Missed words come back after 1, 3, 7, 14 and 30 days |
| Next | Azure Speech pronunciation assessment (phoneme scores), LLM feedback, interview simulator |

## Architecture

```
Browser (PWA) -> FastAPI (Docker) -> PostgreSQL
                                        |
                       phase 3: ADF / Airflow -> ADLS + Delta (bronze, silver)
                       phase 4: dbt + Databricks (gold) -> dashboard
```

## Data model (OLTP)

- `attempts`: one row per spoken attempt; `raw` keeps the full request and result as JSON (future bronze layer)
- `attempt_words`: one row per expected or heard word with status and score (future silver layer)
- `review_items`: spaced repetition state per user and word
- `users`: name and current level

## Run

```bash
cp .env.example .env   # set POSTGRES_PASSWORD, APP_ACCESS_CODE, APP_PORT
docker compose up -d --build
curl http://127.0.0.1:$APP_PORT/api/health
```

API docs: `/api/docs`.
