# Banking App — Phase 1 skeleton

A modular-monolith banking web application: React/TypeScript frontend, FastAPI/SQLAlchemy/Alembic backend, PostgreSQL, Docker Compose. See [arhitectura_aplicatie_bancara.md](arhitectura_aplicatie_bancara.md) for the full domain architecture.

This repository is the **Phase 1 foundation**: auth, users, wallets, transactions + ledger are implemented; every other domain (payments, cards, credit, fraud, rewards, AI agents, ...) is a structured placeholder the team fills in during later phases.

## Tech stack

- **Frontend:** React, TypeScript, React Router
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **Infra:** Docker / Docker Compose
- **AI (future):** Azure AI Foundry, GPT-5-mini only — see [backend/app/ai/README.md](backend/app/ai/README.md)

## Repository structure

```
backend/app/
  auth/ users/ wallets/ transactions/      # implemented (Phase 1)
  fx/ payments/ cards/ rewards/ merchants/
  personal_finance/ credit/ fraud/
  notifications/ exports/ analytics/
  budgets/ savings/ statements/ audit/ business/  # placeholders (later phases)
  ai/client/                                # shared Azure Foundry GPT-5-mini client
  ai/orchestrator/ personal_finance/ credit/ fraud/ tools/  # agent placeholders
backend/migrations/                         # Alembic
backend/tests/
frontend/src/
  pages/        # one route-level component per nav item
  features/     # placeholder folders for feature-specific code (later phases)
  components/ layouts/ hooks/ store/ api/ types/
```

Every implemented backend module follows: `router.py` (HTTP) → `service.py` (business rules) → `repository.py` (data access) → `models.py` / `schemas.py`.

## Database

The shared source of truth is **Supabase Postgres**. Copy `.env.example` to `.env` and fill in `DATABASE_URL` with your project's connection string from Supabase Dashboard → Project Settings → Database → Connection string → URI, tab **Session pooler** (not "Direct connection" — IPv6-only, unreachable from Docker Desktop; not "Transaction pooler" port 6543 — no prepared-statement support). Username format is `postgres.[project-ref]`, not plain `postgres`.

If your network blocks the Supabase pooler (some corporate networks block outbound 5432/6543 entirely), `docker-compose.yml` also defines an optional local `postgres` service — point `DATABASE_URL` at it instead (`postgresql+psycopg://banking:banking@postgres:5432/banking`) for local dev while the network issue gets sorted separately.

## Running with Docker (recommended)

```bash
cp .env.example .env   # then fill in DATABASE_URL (see Database section above)
docker compose up --build
```

This starts the backend (`http://localhost:8000`) and the frontend (`http://localhost:5173`), plus the optional local `postgres` service. Which database the backend actually talks to is controlled by `DATABASE_URL` (see Database section above). The app boots correctly even without Azure AI credentials set — AI functionality isn't part of Phase 1.

Apply migrations and seed data once the containers are up:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

## Running locally without Docker

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\Activate.ps1 for PowerShell
pip install -r requirements-dev.txt
cp ../.env.example ../.env      # fill in DATABASE_URL with your Supabase connection string
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs`. Health check: `http://localhost:8000/health`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Opens at `http://localhost:5173`.

### Tests

```bash
cd backend
source .venv/Scripts/activate
pytest
```

Tests run against an in-memory SQLite database, so they need no Postgres/Docker.

## Seed data

`python -m app.seed` (backend) creates, if not already present:

- `user@example.com` / `Password123!` (role `USER`) with RON (main), EUR and USD wallets, plus two mock card-payment transactions
- `admin@example.com` / `Password123!` (role `ADMIN`)

Not imported by the app itself — run it explicitly after migrating.

## What's implemented (Phase 1)

- FastAPI app, config via env vars, PostgreSQL/SQLAlchemy setup, Alembic with a hand-written Migration 1 (`users, wallets, transactions, wallet_ledger_entries, user_sessions, user_devices`)
- JWT auth (access + refresh), password hashing, `USER`/`ADMIN` roles, register/login
- `User`, `Wallet` (multi-currency, one main wallet, available/reserved balance), `Transaction` + `WalletLedgerEntry` (full status lifecycle enum, paired debit/credit ledger entries)
- A deterministic internal wallet-to-wallet transfer service (`POST /api/v1/transactions/transfer`) demonstrating the end-to-end flow: transfer → ledger entries → balance update, including cross-currency transfers priced via `POST /fx/quote`
- Wallet statements (`GET /api/v1/statements`, `GET /api/v1/statements/export?format=csv|pdf`) — opening/closing balance, totals and transaction list for a wallet over a date range, computed on demand from the ledger
- `/health` and `/api/v1/health`
- React shell: routing, layout, auth context, protected routes, and a working Login → Dashboard → Wallets → Transactions flow against the real API
- Placeholder pages for every nav item (Cards, Payments, Rewards, Analytics, Credit, Assistant, Profile, Admin)
- Backend tests: health, user creation, wallet creation/rules, transaction/ledger service
- `ai/client` — the shared Azure AI Foundry (GPT-5-mini) client abstraction, lazily instantiated so the app runs with no AI credentials configured

## What's intentionally left as placeholder

- Every backend module besides auth/users/wallets/transactions/fx/statements (`payments, cards, rewards, merchants, personal_finance, credit, fraud, notifications, exports, analytics, budgets, savings, audit, business`) — routers exist and return `501` so the route table is stable, but no models/logic yet
- All AI agents (`orchestrator, personal_finance, credit, fraud`) and `ai/tools` — structure only, per the task's explicit instruction not to implement agent logic yet
- Fraud scoring, PENDING_REVIEW flow, cards, credit, business exports, notifications, admin workflows
- Frontend feature folders (`features/*`) — empty placeholders; real feature-specific components/hooks land here as each domain is built

## Known issues / environment notes

- Frontend build verified via `docker compose exec frontend npm run build` (`tsc -b && vite build`) — no local Node.js needed, the frontend container has it.
- **`bcrypt` is pinned to `4.0.1`** in `backend/requirements.txt` — `passlib` 1.7.4 (last release 2020, unmaintained) breaks against `bcrypt>=4.1`'s stricter 72-byte handling.
- **Migration 1 is hand-written**, not autogenerated (no live Postgres instance was available to run `alembic revision --autogenerate` against). Double-check it against the models before your first real deploy: `alembic upgrade head` on a fresh database is the way to verify.
- Statement PDF export uses `fpdf2` (pure Python, no system dependencies) — a plain tabular layout, not a branded document design.

## Branch / work split for the 4 developers

Mirrors architecture.md §40:

- **Dev 1 — Core Banking:** wallets, balances, transaction engine, ledger, FX, statements, PDF/CSV export
- **Dev 2 — Payments:** transfers, phone transfers, beneficiaries, QR payments, scheduled/recurring payments, split bill, transaction folders, business exports
- **Dev 3 — Cards & Credit:** cards (freeze/unfreeze, one-time cards), credit score, credit applications, loans, installments, early repayment
- **Dev 4 — Intelligence & Risk:** analytics, budgets, savings goals, rewards, merchant cashback, fraud engine + admin UI, AI orchestrator and agents

Suggested branch naming: `feature/<dev-area>/<short-description>`, e.g. `feature/payments/qr-flow`. All four branch off `main` once this skeleton is merged; the shared `auth/users/wallets/transactions` modules should be treated as stable contracts — extend, don't restructure, without a heads-up to the team.

## Where the future Azure AI Foundry (GPT-5-mini) integration connects

1. Set the four `AZURE_OPENAI_*` variables in `.env` (see `.env.example`).
2. Every future agent (Orchestrator, Personal Finance, Credit, Fraud Investigation) must call `backend/app/ai/client/azure_foundry_client.py`'s `get_azure_foundry_client()` — never instantiate its own model client.
3. Agents only reach data through **tools** in `backend/app/ai/tools/`, and tools only call backend **services** — never the database directly (`Agent → Tool → Backend Service → Database`).
4. Financial write actions stay two-step: an agent may create a draft (e.g. `create_transfer_draft()`); only the backend executes the real operation, after explicit user confirmation in the UI.
5. Do not add other model providers or fallback logic — GPT-5-mini on Azure AI Foundry is the only supported deployment.
