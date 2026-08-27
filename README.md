# EasyB — banking app

A modular-monolith banking web application: React/TypeScript frontend, FastAPI/SQLAlchemy/Alembic backend, PostgreSQL, Docker Compose. See [docs/architecture.md](docs/architecture.md) and [docs/architecture_diagrams.md](docs/architecture_diagrams.md) for the full domain architecture.

Core banking, payments, cards, credit, rewards, notifications, analytics, onboarding/KYC and a deterministic fraud engine are implemented and merged to `master`. AI agents (Orchestrator, Personal Finance, Credit, Fraud Investigation) are still a structured placeholder — see [backend/app/ai/README.md](backend/app/ai/README.md).

## Tech stack

- **Frontend:** React, TypeScript, React Router
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **Infra:** Docker / Docker Compose
- **AI (future):** Azure AI Foundry, GPT-5-mini only — see [backend/app/ai/README.md](backend/app/ai/README.md)

## Repository structure

```
backend/app/
  auth/ users/ wallets/ transactions/ fx/
  payments/ cards/ credit/ rewards/ merchants/
  notifications/ analytics/ statements/ fraud/
  budgets/ savings/                           # implemented
  exports/ audit/ business/                   # still placeholders (routers return 501)
  ai/client/                                  # shared Azure Foundry GPT-5-mini client
  ai/orchestrator/ personal_finance/ credit/ fraud/ tools/  # agent placeholders
backend/migrations/                           # Alembic
backend/tests/
supabase/sql/                                 # ad-hoc SQL run by hand against the shared Supabase project
  # (schema dumps, seed fixes, cross-branch migration syncs — see docs/supabase_rest_backend.md)
frontend/src/
  pages/        # one route-level component per nav item
  features/     # feature-specific components/hooks (auth onboarding, analytics, ...)
  components/ layouts/ hooks/ store/ api/ types/
```

Every implemented backend module follows: `router.py` (HTTP) → `service.py` (business rules) → `repository.py` (data access) → `models.py` / `schemas.py`.

## Database

The shared source of truth is **Supabase Postgres**. Copy `.env.example` to `.env` and fill in `DATABASE_URL` with your project's connection string from Supabase Dashboard → Project Settings → Database → Connection string → URI, tab **Session pooler** (not "Direct connection" — IPv6-only, unreachable from Docker Desktop; not "Transaction pooler" port 6543 — no prepared-statement support). Username format is `postgres.[project-ref]`, not plain `postgres`.

If your network blocks the Supabase pooler (some corporate networks block outbound 5432/6543 entirely), `docker-compose.yml` also defines an optional local `postgres` service — point `DATABASE_URL` at it instead (`postgresql+psycopg://banking:banking@postgres:5432/banking`) for local dev while the network issue gets sorted separately.

If direct Postgres ports are blocked entirely (no 5432/6543 outbound at all, only HTTPS), set `DATABASE_BACKEND=supabase_rest` instead and talk to Supabase over its REST API — see [docs/supabase_rest_backend.md](docs/supabase_rest_backend.md) for setup and current endpoint coverage.

## Running with Docker (recommended)

```bash
cp .env.example .env   # then fill in DATABASE_URL (see Database section above)
docker compose up --build
```

This starts the backend (`http://localhost:8000`) and the frontend (`http://localhost:5173`), plus the optional local `postgres` service. Which database the backend actually talks to is controlled by `DATABASE_URL` (see Database section above). The app boots correctly even without Azure AI credentials set — the AI agents aren't implemented yet.

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

We don't have `npm`/Node.js installed locally on dev machines — run the frontend through Docker instead, even when the backend runs locally:

```bash
cp .env.example .env
docker compose up --build frontend
```

Opens at `http://localhost:5173`. If the backend isn't already running locally, either start it with `uvicorn` as above (in another terminal) or bring it up alongside via `docker compose up --build backend frontend`.

If you do have `npm` available (e.g. CI, or a machine that has Node installed), the native flow is:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Tests

```bash
cd backend
source .venv/Scripts/activate
pytest
```

Tests run against an in-memory SQLite database, so they need no Postgres/Docker.

To run them inside the running `backend` container instead, `requirements-dev.txt` isn't baked into its image (only `requirements.txt` is), so install it into the container first: `docker compose exec backend pip install -r requirements-dev.txt`, then `docker compose exec backend python -m pytest`.

## Seed data

`python -m app.seed` (backend) creates, if not already present:

- `user@example.com` / `Password123!` (role `USER`) with RON (main), EUR and USD wallets, plus two mock card-payment transactions
- `admin@example.com` / `Password123!` (role `ADMIN`)

Not imported by the app itself — run it explicitly after migrating.

## What's implemented

- JWT auth (access + refresh), password hashing, `USER`/`ADMIN` roles, register/login, optional referral code at registration
- Multi-user onboarding: KYC placeholder, address, employment profile, full profile editing
- `User`, `Wallet` (multi-currency, opt-in additional currencies, one main wallet, available/reserved balance), `Transaction` + `WalletLedgerEntry` (full status lifecycle enum, paired debit/credit ledger entries)
- Wallet-to-wallet transfers, live FX quoting (Frankfurter/ECB market rate + bank margin) and cross-currency exchange, wallet close/reopen
- Payments: phone/IBAN transfers, beneficiaries, QR payment requests, scheduled/recurring payments, split bill, transaction folders
- Cards: tiers, freeze/unfreeze, secure mock details, card payment preferences, stored credit card accounts
- Credit: score, applications, loans, loan calculator, multi-currency credit profiles
- Rewards & merchant cashback: points ledger, tiers, redeemable benefits, cashback offers
- Notifications: built once, wired into transfers, split bills, cashback, credit and registration across every domain
- Analytics: spending breakdown, trends, net worth (with history/forecast), monthly trend series
- Wallet statements (`GET /api/v1/statements`, `GET /api/v1/statements/export?format=csv|pdf`)
- Business transaction export (`/api/v1/exports`: preview, generate, list export history, download)
- A deterministic fraud engine (rule-based scoring, evidence tracking) plus an admin fraud-review dashboard section — the engine flags/holds, a human makes the final call
- Budgets and savings goals
- `/health` and `/api/v1/health`
- React app: routing, layout, auth context (with idle logout), protected routes, onboarding flow, and working pages for every domain above
- Backend test suite covering all of the above (see `backend/tests/`)
- `ai/client` — the shared Azure AI Foundry (GPT-5-mini) client abstraction, lazily instantiated so the app runs with no AI credentials configured

## What's still a placeholder

- All AI agents (`orchestrator, personal_finance, credit, fraud`) and `ai/tools` — structure only; agents must go `Agent → Tool → Backend Service → Database`, never straight to the DB
- Loan servicing: no endpoint to pay down an existing loan's principal or run an early-repayment simulation, despite `EARLY_REPAYMENT` existing as an enum value — the loan calculator only simulates a schedule
- Admin audit log

## Known issues / environment notes

- Frontend build verified via `docker compose exec frontend npm run build` (`tsc -b && vite build`) — no local Node.js needed, the frontend container has it.
- **`bcrypt` is pinned to `4.0.1`** in `backend/requirements.txt` — `passlib` 1.7.4 (last release 2020, unmaintained) breaks against `bcrypt>=4.1`'s stricter 72-byte handling.
- **Migration 1 is hand-written**, not autogenerated (no live Postgres instance was available to run `alembic revision --autogenerate` against). Double-check it against the models before your first real deploy: `alembic upgrade head` on a fresh database is the way to verify.
- Statement PDF export uses `fpdf2` (pure Python, no system dependencies) — a plain tabular layout, not a branded document design.
- **Alembic revision ids must stay ≤32 characters.** `alembic_version.version_num` is `varchar(32)` by default; a longer merge-migration id crashes `alembic upgrade head` with `StringDataRightTruncation` for everyone on a clean database. This has bitten the team more than once when naming merge migrations after long branch names — keep merge-migration ids short (e.g. `0027_merge_heads`, not a concatenation of both parent names).
- With 4 people branching in parallel, Alembic ends up with multiple heads regularly. Run `alembic heads` before opening a PR; if there's more than one, add a merge migration (`down_revision` as a tuple) rather than rewriting either side's migration.

## Branch / work split for the 4 developers

Mirrors [docs/architecture.md](docs/architecture.md) §40:

- **Dev 1 — Core Banking:** wallets, balances, transaction engine, ledger, FX, statements, PDF/CSV export
- **Dev 2 — Payments:** transfers, phone transfers, beneficiaries, QR payments, scheduled/recurring payments, split bill, transaction folders, business exports
- **Dev 3 — Cards & Credit:** cards (freeze/unfreeze, one-time cards), credit score, credit applications, loans, installments, early repayment
- **Dev 4 — Intelligence & Risk:** analytics, budgets, savings goals, rewards, merchant cashback, fraud engine + admin UI, AI orchestrator and agents

Suggested branch naming: `feature/<dev-area>/<short-description>`, e.g. `feature/payments/qr-flow`. All four branch off `master` and merge back via PR; the shared `auth/users/wallets/transactions` modules should be treated as stable contracts — extend, don't restructure, without a heads-up to the team. See [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md) for the full cross-agent collaboration rules.

## Where the future Azure AI Foundry (GPT-5-mini) integration connects

1. Set the four `AZURE_OPENAI_*` variables in `.env` (see `.env.example`).
2. Every future agent (Orchestrator, Personal Finance, Credit, Fraud Investigation) must call `backend/app/ai/client/azure_foundry_client.py`'s `get_azure_foundry_client()` — never instantiate its own model client.
3. Agents only reach data through **tools** in `backend/app/ai/tools/`, and tools only call backend **services** — never the database directly (`Agent → Tool → Backend Service → Database`).
4. Financial write actions stay two-step: an agent may create a draft (e.g. `create_transfer_draft()`); only the backend executes the real operation, after explicit user confirmation in the UI.
5. Do not add other model providers or fallback logic — GPT-5-mini on Azure AI Foundry is the only supported deployment.
