# AI SMS Guard

AI SMS Guard is a simple queue-based SMS delivery pipeline (RabbitMQ) focused on cost and risk control. Messages are first stored in Postgres and published to a queue. A worker then applies a rule engine to decide whether to send immediately or escalate to an "AI Guard" (to avoid duplicates, expensive multipart messages, or risky retries).

This project is meant to simulate/test scenarios like:

- Preventing duplicate SMS sends (cost reduction + fewer user complaints)
- Managing retries for temporary/permanent failures and sending suspicious cases to a DLQ
- Using AI only when needed (cost-aware)
- A lightweight dashboard for stats and cost estimates

Additionally, by leveraging AI and analyzing historical data, we can take a user's phone number and desired time as input, and predict the probability (between 0 and 1) of the message successfully reaching the user, as well as suggest the optimal time to send the message.


## Architecture at a glance

- `backend` (FastAPI): accepts `/sms`, stores events in Postgres, publishes messages to RabbitMQ
- `worker` (Python): consumes the main queue and DLQ, runs the rule engine, calls the AI Guard (OpenRouter) when needed (main queue review path only)
- `postgres`: stores SMS events and AI call logs
- `rabbitmq`: queues (`sms_main`, `sms_dlq`)
- `redis`: dedup window keys (Scenario 5) + daily AI rate limit counter (resets at midnight)
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

### 4) Test

After setting up and running the full project, you can populate the database with sample test data by running:

```bash
docker exec -it backend_dev python data_test.py
```

This will add sample message history for the phone number:
##### 09123456789

Once the data is loaded, open the Streamlit dashboard at:

<http://localhost:8501>

From the sidebar, you can navigate to different pages and explore the following features:

- View cost statistics – track your estimated SMS spending
- Send a test SMS – try sending a message to any phone number
- AI-powered delivery prediction – enter a phone number and desired time to get:
  - A probability score (0 to 1) indicating how likely the message is to reach the user
  - The best suggested time to send the message for maximum delivery chance

Tip: For testing the AI prediction feature, use the number 09123456789 — it already has sample historical data in the database to generate meaningful predictions.

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
- OpenRouter (AI Guard) settings:
  - `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, `OPENROUTER_TIMEOUT`
  - `AI_DAILY_CALL_LIMIT`, `REDIS_URL` (Redis: Scenario 5 dedup + daily rate limit; UTC-based)

## Repository layout

- `backend/`: API, models, Alembic migrations, async DB connection
- `worker/`: queue consumers, rule engine, AI guard, sync DB connection
- `streamlit/`: dashboard
- `docker-compose.dev.yml`: local dev stack
