-- Supabase manual update for migration 0037_savings_goal_contributions.
--
-- Adds SAVINGS_CONTRIBUTION / SAVINGS_WITHDRAWAL to transaction_type (a
-- real Transaction + WalletLedgerEntry now backs a savings contribution,
-- instead of savings_goals.current_amount just being incremented in
-- place) and a status column to savings_goals (ACTIVE / COMPLETED /
-- WITHDRAWN).
--
-- Written idempotent and independent of the shared project's current
-- alembic_version state, same reasoning as
-- supabase_budget_merchant_category_update.sql. Does NOT touch
-- alembic_version.

BEGIN;

ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'SAVINGS_CONTRIBUTION';
ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'SAVINGS_WITHDRAWAL';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'savings_goal_status') THEN
    CREATE TYPE savings_goal_status AS ENUM ('ACTIVE', 'COMPLETED', 'WITHDRAWN');
  END IF;
END $$;

ALTER TABLE savings_goals ADD COLUMN IF NOT EXISTS status savings_goal_status NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE savings_goals ALTER COLUMN status DROP DEFAULT;

COMMIT;
