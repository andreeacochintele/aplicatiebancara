# Team Supabase Workflow

This project can run locally in Docker while using one shared Supabase cloud
database through HTTPS.

## 1. Local `.env`

Every developer should use the same Supabase project:

```env
DATABASE_BACKEND=supabase_rest

POSTGRES_USER=banking
POSTGRES_PASSWORD=banking
POSTGRES_DB=banking
DATABASE_URL=postgresql+psycopg://banking:banking@postgres:5432/banking

SUPABASE_URL=https://qofftbfxgcexooaatcae.supabase.co
SUPABASE_KEY=your_backend_secret_or_service_role_key_here

JWT_SECRET_KEY=any-long-random-local-secret
FRONTEND_ORIGIN=http://localhost:5173

AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_DEPLOYMENT_NAME=
```

`SUPABASE_KEY` must be a backend secret key or legacy `service_role` key. Never
put it in frontend env files, screenshots, GitHub, Discord, Teams, or browser
code.

## 2. When Does Supabase Need Updating?

Check every merged PR. Supabase needs a schema update when the PR changes files
inside:

```text
backend/migrations/versions/
```

Typical examples:

- new table
- new column
- new enum
- changed constraint
- required default/demo rows used by the app

Supabase usually does not need updating for:

- frontend-only changes
- backend logic that does not change models/migrations
- CSS/layout changes
- tests only

## 3. How To Update Supabase Schema

Only one person should do this after a DB-changing PR is merged.

1. Pull latest main:

```powershell
git checkout master
git pull
```

2. Start Docker:

```powershell
docker compose up -d
```

3. Generate SQL from Alembic:

```powershell
docker compose exec backend alembic upgrade head --sql > supabase_update.sql
```

4. Open Supabase:

```text
Supabase Dashboard -> SQL Editor -> New query
```

5. Paste the SQL from `supabase_update.sql` and run it.

If Supabase says a table/column already exists, stop and check which migrations
were already applied. Do not randomly delete tables or rerun destructive SQL.

## 4. Current Extra SQL Helpers

If the cloud DB was created before rewards/merchants existed, run:

```text
supabase_rewards_merchants_schema.sql
```

Cards also need the latest card migrations applied in Supabase:

```text
0011_card_tiers
0012_card_mock_cvv
0013_card_mock_pan
```

These add:

```text
cards.tier
cards.mock_cvv
cards.mock_pan
```

## 5. Seed Shared Data

After schema updates, run:

```powershell
docker compose exec backend python -m app.seed --supabase-rest
```

Seed is safe to rerun for our demo data. It skips existing base users and fills
missing rewards/merchants data.

## 6. How To Test If Supabase Is Updated

Start the app:

```powershell
docker compose down
docker compose up --build
```

Login:

```text
user@example.com / Password123!
```

Quick visual checks:

- Dashboard loads without backend 500 errors.
- Payments -> Transfer shows saved beneficiaries.
- Payments -> By phone can find `+40700000003`.
- Cards page loads without missing-column errors.
- Rewards/Merchants pages or cards load without `table not found` errors.

Strong shared-database test:

1. Dev A creates a beneficiary named `LIVE TEST DEV A`.
2. Dev B pulls latest code, uses the same Supabase env, starts Docker.
3. Dev B logs into the same user and refreshes Payments.
4. Dev B should see `LIVE TEST DEV A`.

The database update is live immediately, but the frontend may need refresh or a
new API fetch.

## 7. How To Share Supabase Permissions

Preferred way: invite teammates to the Supabase project/organization.

1. Open Supabase Dashboard.
2. Go to the organization/team settings.
3. Invite each teammate by email.
4. Use a role that matches what they need:
   - `Developer`: good default for normal project work.
   - `Administrator`: only for people who must manage project settings and keys.
   - `Owner`: only for trusted project owners.

Supabase docs define these roles as organization/project access controls. Avoid
making everyone Owner unless truly needed.

## 8. How To Share The Backend Key

Best option: after teammates accept the invite, they get the backend key from:

```text
Supabase Dashboard -> Project Settings -> API Keys
```

Use a secret key or legacy `service_role` key for the backend only.

If you must send the key manually, use a secure password manager/share link.
Do not paste it into GitHub, the frontend, screenshots, or normal chat.

If the key was exposed publicly, rotate/delete it in Supabase and update every
developer's `.env`.

## 9. Team Message After Updating Supabase

Use this message:

```text
Supabase schema is updated to latest master.
Please pull latest master, update .env if needed, and restart Docker:

git pull
docker compose down
docker compose up --build
```
