# Supabase REST Backend Mode

Use this mode when direct Postgres ports `5432` / `6543` are blocked but HTTPS
to Supabase works.

## Environment

```env
DATABASE_BACKEND=supabase_rest
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-backend-service-role-key
```

Do not put the service-role key in the frontend. It is backend-only.

`DATABASE_URL` can stay configured for local Postgres, but it is not used while
`DATABASE_BACKEND=supabase_rest`.

## Schema And Migrations

Supabase REST cannot run Alembic migrations. When direct database ports are
blocked, generate SQL locally and run it in the Supabase SQL Editor:

```powershell
docker compose exec backend alembic upgrade head --sql > supabase_schema.sql
```

Then paste the SQL into:

```text
Supabase Dashboard -> SQL Editor
```

If the shared Supabase database was already created before the rewards and
merchants migrations landed, run only `supabase_rewards_merchants_schema.sql`
instead of replaying the full schema.

## Seed Data

After the schema exists in Supabase:

```powershell
docker compose exec backend python -m app.seed --supabase-rest
```

## Current Coverage

The first REST-backed slice supports:

- auth login/register/session creation
- current-user lookup
- wallet list/create
- transaction list/get
- same-currency internal transfers
- beneficiaries CRUD
- phone transfers
- same-currency and FX-backed IBAN transfers
- QR payment requests
- scheduled payments
- FX quote creation and acceptance through payment flows
- cards list/create/freeze/unfreeze
- card payment preferences
- credit profile and score
- credit score recalculation
- credit applications
- loan calculator
- loans created from approved applications
- budgets create/list with category spend tracking
- savings goals create/list/contribute
- merchants catalog
- cashback offers
- merchant purchase reward recording
- reward account/tier/benefit reads
- reward points and benefit redemption
- analytics spending, trends, net worth and forecast reads
- statements generation and export data reads

AI agent wrappers still depend on the backend services beneath them; they should
not call Supabase directly.
