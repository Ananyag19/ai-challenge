# magicpin AI Challenge — Candidate Bot (foundation)

Stateful FastAPI bot that implements the official HTTP contract from `challenge-testing-brief.md`.

This step is the **backend foundation only**. Trigger ranking and LLM message composition are stubbed: `/v1/tick` currently returns `{ "actions": [] }` after deterministic eligibility checks.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with team metadata. Do not commit `.env`.

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

`PORT` and `HOST` can be set via environment variables.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/healthz` | Liveness and context counts |
| GET | `/v1/metadata` | Team identity |
| POST | `/v1/context` | Versioned context ingest |
| POST | `/v1/tick` | Simulated clock / outbound planning |
| POST | `/v1/reply` | Merchant or customer reply |

## Tests

```bash
pytest -q
```

## Local judge (after the composer exists)

```bash
python judge_simulator.py
```

Do not edit `judge_simulator.py` or the official dataset files for this bot.
