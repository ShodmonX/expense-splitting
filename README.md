# Telegram Group Expense Bot (Clean Chat)

Telegram group bot for apartment expense tracking with a single pinned dashboard per group.

## Features

- One ledger per Telegram group chat
- Clean chat UX:
  - delete user command messages
  - wizards run in one bot message via inline keyboards
  - wizard message is deleted after completion/cancel
  - dashboard is edited (no spam)
- Amounts are entered in **thousands of UZS** and stored as `amount_k` (integer)
- Member types:
  - residents: always included in ROOM expenses
  - non-residents: can be selected in SPLIT expenses
- Expense types:
  - `/room` (ROOM / xona harajati): participants = all residents
  - `/split` (SPLIT / oddiy harajat): participants selected
  - `/pay` (TRANSFER): direct payment between two members

## Tech Stack

- Python 3.11+
- aiogram v3 (async)
- SQLAlchemy 2.0 (async ORM)
- asyncpg + PostgreSQL
- Alembic migrations
- Docker + docker-compose

## Local Run (recommended DB via Docker)

1. Create and activate a virtualenv, install deps:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start Postgres:

```bash
cp .env.example .env
# edit .env and set BOT_TOKEN
docker compose up -d postgres
```

3. Export env vars (or use your shell tooling):

```bash
set -a
source .env
set +a
```

4. Run migrations:

```bash
alembic upgrade head
```

5. Start the bot:

```bash
python3 -m expense_splitting_bot.bot.main
```

## Docker Run (bot + postgres)

```bash
cp .env.example .env
# edit .env and set BOT_TOKEN
docker compose up --build
```

The bot container runs `alembic upgrade head` on startup.

## Commands

- `/setup` (admin only): toggle residents via inline list
- `/add_member` (admin only, reply): add a user who hasn’t been seen by the bot yet
- `/room`: ROOM expense wizard
- `/split`: SPLIT expense wizard
- `/pay`: TRANSFER wizard
- `/balance`: show balances (temporary message with “Close”)
- `/settle`: show settlement suggestions (temporary message with “Close”)
- `/report` (admin only): ROOM total + per-resident ROOM shares + balances + settlement
