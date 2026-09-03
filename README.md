# EasyB — banking app

A modular-monolith banking web application: React/TypeScript frontend, FastAPI/SQLAlchemy/Alembic backend, PostgreSQL, Docker Compose. See [docs/architecture.md](docs/architecture.md) and [docs/architecture_diagrams.md](docs/architecture_diagrams.md) for the full domain architecture.

Core banking, payments, cards, credit, rewards, notifications, analytics, onboarding/KYC, business accounts (profiles, ANAF/CUI lookup, KYB document verification, bulk transfers, recurring templates, transaction export), a deterministic fraud engine and an AI assistant (Orchestrator + Personal Finance, Credit, Support and Actions agents, all on Azure AI Foundry GPT-5-mini) are implemented and merged to `master` — see [backend/app/ai/README.md](backend/app/ai/README.md) for the AI layer's architecture and guardrails.

## Tech stack

- **Frontend:** React, TypeScript, React Router
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **Infra:** Docker / Docker Compose
- **AI:** Azure AI Foundry, GPT-5-mini only — see [backend/app/ai/README.md](backend/app/ai/README.md)

## Repository structure

```
backend/app/
  auth/ users/ wallets/ transactions/ fx/
  payments/ cards/ credit/ rewards/ merchants/
  notifications/ analytics/ statements/ fraud/
  budgets/ savings/ business/ exports/ audit/  # implemented
  reconciliation/                             # admin: wallet balance vs ledger-entry sanity check
  personal_finance/                           # still a placeholder (router returns 501) — distinct
                                               #   from ai/personal_finance/, which is implemented
  ai/client/                                  # shared Azure Foundry GPT-5-mini client
  ai/orchestrator/                            # intent routing across the agents below
  ai/personal_finance/ credit/ support/ actions/  # implemented agents
  ai/fraud/ tools/                            # fraud investigation support: future/out of scope
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

This starts the backend (`http://localhost:8000`) and the frontend (`http://localhost:5173`), plus the optional local `postgres` service. Which database the backend actually talks to is controlled by `DATABASE_URL` (see Database section above). The app boots correctly even without Azure AI credentials set — the shared Azure Foundry client is lazily instantiated, so anything not touching the AI assistant works normally, and AI endpoints fail gracefully rather than crashing the app.

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
- `admin@example.com` / `admin` (role `ADMIN`)
- `business@example.com` / `Password123!` (`user_type` `BUSINESS`) with a RON (main), EUR and USD wallet — use this account for the business-account pages (company profile/KYB, bulk transfers, recurring templates, transaction export)

Not imported by the app itself — run it explicitly after migrating.

## What's implemented

- JWT auth (access + refresh), password hashing, `USER`/`ADMIN` roles, register/login, optional referral code at registration
- Multi-user onboarding: KYC placeholder, address, employment profile, full profile editing
- `User`, `Wallet` (multi-currency, opt-in additional currencies, one main wallet, available/reserved balance), `Transaction` + `WalletLedgerEntry` (full status lifecycle enum, paired debit/credit ledger entries)
- Wallet-to-wallet transfers, live FX quoting (Frankfurter/ECB market rate + bank margin) and cross-currency exchange, wallet close/reopen
- Payments: phone/IBAN transfers (with BIC validation), beneficiaries, QR payment requests, scheduled/recurring payments, split bill, transaction folders, bulk/payroll-style transfers with CSV/Excel upload (AI-assisted extraction for messy files), batch history, saved recurring bulk-transfer templates (create, edit, pause/resume/cancel, run on demand)
- Cards: tiers, freeze/unfreeze, secure mock details, card payment preferences, stored credit card accounts
- Credit: score, applications, loans, loan calculator, multi-currency credit profiles, full loan servicing — installment schedule, regular installment payments, early-repayment simulation and execution
- Rewards & merchant cashback: points ledger, tiers, redeemable benefits, cashback offers
- Notifications: built once, wired into transfers, split bills, cashback, credit and registration across every domain
- Analytics: spending breakdown, trends, net worth (with history/forecast), monthly trend series
- Wallet statements (`GET /api/v1/statements`, `GET /api/v1/statements/export?format=csv|pdf`)
- Business accounts: company profiles (multiple companies per user), automatic company lookup by CUI/tax ID via ANAF's public registry, KYB document verification (registration certificate, articles of association, legal representative ID) with an admin review queue — same "engine flags, admin decides" shape as fraud, business transaction export (`/api/v1/exports`: preview, generate, list export history, download)
- A deterministic fraud engine (rule-based scoring, evidence tracking) plus an admin fraud-review dashboard (pending queue + decided-case history) — the engine flags/holds, a human makes the final call; an admin-triggered AI Fraud Investigation agent (`ai/fraud/`, not orchestrator-routed) adds a cached, advisory qualitative read alongside the unchanged deterministic score, never the decision itself — see [backend/app/ai/fraud/README.md](backend/app/ai/fraud/README.md)
- Admin: audit log (every admin decision, before/after state), reconciliation check (wallet balance vs its own ledger entries)
- Budgets and savings goals
- AI assistant: Orchestrator + Personal Finance, Credit, Support and Actions agents (chat-facing, `ai/orchestrator/registry.py`), plus the admin-only Fraud Investigation agent above — all on the shared Azure AI Foundry (GPT-5-mini) client (`ai/client`, lazily instantiated so the app runs with no AI credentials configured); Actions can prepare and, after explicit user confirmation, execute a phone/name transfer
- `/health` and `/api/v1/health`
- React app: routing, layout, auth context (with idle logout), protected routes, onboarding flow, and working pages for every domain above
- Backend test suite covering all of the above (see `backend/tests/`)

## What's still a placeholder

- `app/personal_finance/` (the non-AI module — router returns 501). Superseded in practice by `analytics`/`budgets`/`savings` plus the chat-facing AI Personal Finance agent (`ai/personal_finance/`, which *is* implemented)
- Routing-agent transfers (Actions agent) don't yet go through the full deterministic fraud engine — only the card-payment HOLD/approve path does; the Actions agent currently does a lighter pre-execution fraud screen instead
- `backend/app/ai/README.md` still says "Fraud is untouched/out of scope for the orchestrator" — stale as of the Fraud Investigation agent's implementation; worth a doc fix, not a code gap (the agent itself is admin-triggered by design, not orchestrator-routed, so this was never meant to change)

## Known issues / environment notes

- Frontend build verified via `docker compose exec frontend npm run build` (`tsc -b && vite build`) — no local Node.js needed, the frontend container has it.
- **`bcrypt` is pinned to `4.0.1`** in `backend/requirements.txt` — `passlib` 1.7.4 (last release 2020, unmaintained) breaks against `bcrypt>=4.1`'s stricter 72-byte handling.
- **Migration 1 is hand-written**, not autogenerated (no live Postgres instance was available to run `alembic revision --autogenerate` against). Double-check it against the models before your first real deploy: `alembic upgrade head` on a fresh database is the way to verify.
- Statement PDF export uses `fpdf2` (pure Python, no system dependencies) — a plain tabular layout, not a branded document design.
- **Alembic revision ids must stay ≤32 characters.** `alembic_version.version_num` is `varchar(32)` by default; a longer merge-migration id crashes `alembic upgrade head` with `StringDataRightTruncation` for everyone on a clean database. This has bitten the team more than once when naming merge migrations after long branch names — keep merge-migration ids short (e.g. `0027_merge_heads`, not a concatenation of both parent names).
- With 4 people branching in parallel, Alembic ends up with multiple heads regularly. Run `alembic heads` before opening a PR; if there's more than one, add a merge migration (`down_revision` as a tuple) rather than rewriting either side's migration.
- **When `DATABASE_BACKEND=supabase_rest`, a schema migration only takes effect once its matching file in `supabase/sql/` is run by hand in the Supabase SQL Editor** — `alembic upgrade head` alone only updates the local dev/test Postgres, never the live Supabase project. Shipping backend code (a new required response field, a new column read/written by a service) before that SQL runs makes the live app 500 on that endpoint immediately, even though tests pass — the endpoint tries to read/write a column Supabase doesn't have yet. This isn't hypothetical: one such gap (`0015_credit_lifecycle`'s SQL file existed but had never actually been run) sat undiscovered on the shared Supabase project for weeks, silently breaking loan detail pages, until a full-app sweep the day before a demo caught it. Before merging any migration, treat the corresponding `supabase/sql/*.sql` file as part of the same change, and after running it, verify with a direct REST call (`select=<the new column>`) rather than trusting a 200 from the app's own endpoint — PostgREST can return `200` with quietly incomplete data for a missing column depending on the query shape.
- **`alembic_version` on the shared Supabase project has accumulated multiple stale/orphaned rows** (from past merge-migration reconciliations that never got fully applied there) instead of the single row a fresh database would have. This means `UPDATE alembic_version SET version_num = X WHERE version_num = Y` bookkeeping statements in a `supabase/sql/*.sql` script can silently match zero rows — the actual `CREATE TABLE`/`ALTER TABLE` in the same script still applies correctly, but the version bookkeeping quietly falls further out of sync. Functionally harmless (the DDL is what the app depends on, not this table), but don't trust `alembic_version`'s contents on Supabase as a reliable record of what's been applied — verify schema state directly instead.

## Branch / work split for the 4 developers

Mirrors [docs/architecture.md](docs/architecture.md) §40:

- **Dev 1 — Core Banking:** wallets, balances, transaction engine, ledger, FX, statements, PDF/CSV export
- **Dev 2 — Payments:** transfers, phone transfers, beneficiaries, QR payments, scheduled/recurring payments, split bill, transaction folders, business exports
- **Dev 3 — Cards & Credit:** cards (freeze/unfreeze, one-time cards), credit score, credit applications, loans, installments, early repayment
- **Dev 4 — Intelligence & Risk:** analytics, budgets, savings goals, rewards, merchant cashback, fraud engine + admin UI, AI orchestrator and agents

Suggested branch naming: `feature/<dev-area>/<short-description>`, e.g. `feature/payments/qr-flow`. All four branch off `master` and merge back via PR; the shared `auth/users/wallets/transactions` modules should be treated as stable contracts — extend, don't restructure, without a heads-up to the team. See [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md) for the full cross-agent collaboration rules.

## How the Azure AI Foundry (GPT-5-mini) integration is wired

1. Set the four `AZURE_OPENAI_*` variables in `.env` (see `.env.example`) to actually run the AI agents; the app boots and everything else works without them.
2. Every agent (Orchestrator, Personal Finance, Credit, Support, Actions, Fraud Investigation) calls `backend/app/ai/client/azure_foundry_client.py`'s `get_azure_foundry_client()` — never instantiates its own model client.
3. Agents only reach data through **tools** in each agent's own `tools.py`, and tools only call backend **services** — never the database directly (`Agent → Tool → Backend Service → Database`).
4. Financial write actions stay two-step: an agent creates a draft (e.g. the Actions agent's phone/name-transfer draft); only the backend executes the real operation, after explicit user confirmation in the UI.
5. Do not add other model providers or fallback logic — GPT-5-mini on Azure AI Foundry is the only supported deployment.

See [backend/app/ai/README.md](backend/app/ai/README.md) for the full architecture, guardrails, and how to watch a chat request's orchestration live via the logs.
