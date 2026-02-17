# AI SMS Guard

AI SMS Guard is a simple queue-based SMS delivery pipeline (RabbitMQ) focused on cost and risk control. Messages are first stored in Postgres and published to a queue. A worker then applies a rule engine to decide whether to send immediately or escalate to an “AI Guard” (to avoid duplicates, expensive multipart messages, or risky retries).

This project is meant to simulate/test scenarios like:
- Preventing duplicate SMS sends (cost reduction + fewer user complaints)
- Managing retries for temporary/permanent failures and sending suspicious cases to a DLQ
- Using AI only when needed (cost-aware)
- A lightweight dashboard for stats and cost estimates

## Architecture at a glance

- `backend` (FastAPI): accepts `/sms`, stores events in Postgres, publishes messages to RabbitMQ
- `worker` (Python): consumes the main queue and DLQ, runs the rule engine, calls the AI Guard (OpenRouter) when needed
- `postgres`: stores SMS events and AI call logs
- `rabbitmq`: queues (`sms_main`, `sms_dlq`)
- `redis`: daily AI rate limit counter (resets at midnight)
- `streamlit`: stats + cost estimate dashboard

## Tech stack

- Python 3.12
- FastAPI + Uvicorn
- PostgreSQL + SQLAlchemy (async) + Alembic
- RabbitMQ (management UI on `:15672`)
- Streamlit
- OpenRouter API (optional; only used by the AI Guard)
- Docker Compose (local environment)

## Run locally (recommended: Docker Compose)

### Prerequisites
- Docker and Docker Compose
- (Optional) `make`

### 1) Environment file

Create a local `.env` from the template:

```bash
cp .env.example .env
```

> **Important:** Set `OPENROUTER_API_KEY` in `.env` **before running**.  
> Without it, the AI Guard defaults to `DROP`, so the worker will block/drop messages that require AI review (making the project largely unusable for its intended purpose).

### 2) Start services

Using the Makefile:

```bash
make run
```

Or directly with Docker Compose:

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

### 3) Endpoints

- Backend: `http://localhost:8000`
- Streamlit Dashboard + SMS Test: `http://localhost:8501`
- RabbitMQ Management: `http://localhost:15672` (see `docker-compose.dev.yml` for ports)

### 4) Quick test

Queue an SMS:

```bash
curl -X POST "http://localhost:8000/sms" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+989121234567","body":"Hello! This is a test message."}'
```

Fetch stats:

```bash
curl "http://localhost:8000/stats"
```

Or use Streamlit:
- Open `http://localhost:8501` and use the **ارسال SMS (تست سامانه)** page in the sidebar.

### 5) Stop services

```bash
make down
```

To remove the database volume:

```bash
make down-v
```

## Key configuration (summary)

All key env vars are listed in `.env.example`. The most important ones:
- `DATABASE_URL` / `DATABASE_URL_SYNC`: Postgres connection strings (backend async, worker sync)
- `RABBITMQ_URL` and queue names: `RABBITMQ_MAIN_QUEUE`, `RABBITMQ_DLQ`
- Rule engine thresholds:
  - `DUPLICATE_WINDOW_SECONDS`
  - `MAX_RETRY_BEFORE_DLQ`
  - `MULTIPART_SEGMENT_THRESHOLD`
- OpenRouter (AI Guard) settings:
  - `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, `OPENROUTER_TIMEOUT`
  - `AI_DAILY_CALL_LIMIT`, `REDIS_URL` (daily rate limit via Redis; UTC-based)

## Repository layout

- `backend/`: API, models, Alembic migrations, async DB connection
- `worker/`: queue consumers, rule engine, AI guard, sync DB connection
- `streamlit/`: dashboard
- `docker-compose.dev.yml`: local dev stack

## Development notes

- When `APP_ENV=DEV`, `backend`, `worker`, and `streamlit` auto-reload on code changes.
