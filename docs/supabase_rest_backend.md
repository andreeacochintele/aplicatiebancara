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

As of `0030_fraud_unusual_time`: the last checkpoint any file reached was
`0026_fraud_cases`. `supabase/sql/supabase_advance_to_0030_fraud_unusual_time.sql`
carries it the rest of the way (credit_card_accounts, admin_audit_logs,
ai_conversation_messages, and the fraud_flag_code UNUSUAL_TIME value) — run
it after `supabase_fraud_cases.sql`.

As of `0031_ai_conversations`: run `supabase/sql/supabase_ai_conversations.sql`
after the file above. It adds the `ai_conversations` table and backfills
every existing `ai_conversation_messages` row into one "Legacy conversation"
per user — it prints before/after row counts via `RAISE NOTICE` and aborts
the whole transaction if anything doesn't match, since this is the one
schema change so far that rewrites existing shared rows rather than only
adding new ones.

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
