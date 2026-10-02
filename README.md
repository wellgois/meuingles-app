# MeuInglês

A speaking coach for technical English in data engineering. You talk, the app scores what you said word by word, keeps a spaced-repetition notebook of the words you miss, and suggests sentences to practice. It is also the source system of a data platform built with the tools of my data engineering postgraduate course.

Live at `meuingles.wellgois.com`.

## Current status: phase 1.2

| Part | Status |
| --- | --- |
| Speech capture | Levels 1-2: 16 kHz WAV recorded in the browser and scored by Azure Speech pronunciation assessment (phoneme level). Levels 3-4: browser speech recognition |
| Feedback | Levels 3-4: Claude corrects grammar, rewrites the answer in natural English and generates practice sentences |
| Scoring | Word alignment between target and transcript (`difflib`), per-word status: ok, close, wrong, missing, extra |
| Levels | 1 Sounds & Words, 2 Sentences, 3 Explain it, 4 Your projects (STAR) |
| Level up | 5 attempts in a row scoring 80 or more |
| Review notebook | Missed words come back after 1, 3, 7, 14 and 30 days |
| Sound practice | SQL view `phoneme_stats` (JSONB unnest of Azure phoneme scores, first gold-layer prototype) drives drills for the 3 weakest sounds |
| Next | Interview simulator, data pipeline (ADF / Airflow, Databricks, dbt) |

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
