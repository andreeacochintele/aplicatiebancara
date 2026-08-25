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
docker compose exec backend alembic upgrade head --sql > supabase/sql/supabase_schema.sql
```

Then paste the SQL into:

```text
Supabase Dashboard -> SQL Editor
```

If the shared Supabase database was already created before the rewards and
merchants migrations landed, run only
`supabase/sql/supabase_rewards_merchants_schema.sql` instead of replaying the
full schema.

`alembic upgrade head --sql` cannot generate the full chain from scratch:
migration `0016_card_preferences_cascade` does a live catalog lookup
(`context.execute(...).scalar()`) that only works against a real connection,
so offline `--sql` mode crashes partway through. This is why schema changes
are applied to Supabase as small, hand-written, idempotent files under
`supabase/sql/` instead — one per migration (or a few bundled together),
each stating which checkpoint it expects to start from. Check the highest
`version_num` referenced across `supabase/sql/*.sql` to see where the shared
database actually is before running anything new.

As of `0034_widen_alembic_version`: run
`supabase/sql/supabase_advance_to_0034_widen_alembic_version.sql`. It's
written to be safe from *any* prior state (every statement is idempotent —
`IF NOT EXISTS`, or an `UPDATE ... WHERE` that only touches rows still
needing it), so it doesn't matter which of the older per-migration files
under `supabase/sql/` already ran on the shared project or not; just run
this one file. It supersedes `supabase_advance_to_0029_ai_conversation_messages.sql`,
`supabase_advance_to_0030_fraud_unusual_time.sql`, `supabase_ai_conversations.sql`,
`supabase_credit_card_accounts_update.sql` and `supabase_credit_documents_update.sql`
— those are kept for history but shouldn't be run on their own anymore (none
of them advanced the version marker as far as `0030_credit_currency_dates`,
which had no sync script at all until this one).

Also widens `alembic_version.version_num` to `varchar(255)` (was the
default `varchar(32)`) — a merge-migration revision id has overflowed that
column three separate times now (see `backend/migrations/versions/0034_widen_alembic_version_column.py`),
so this removes the failure mode instead of relying on everyone remembering
a 32-char naming limit.

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
