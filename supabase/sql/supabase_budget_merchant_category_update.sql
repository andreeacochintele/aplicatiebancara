-- Supabase manual update for migration 0036_budget_merchant_category.
--
-- Replaces budgets.category_id (pointed at a transaction_categories table
-- that was never actually created, no FK ever existed) with a plain
-- budgets.category text column matching merchants.category (Retail, Food,
-- Travel, ...) -- the same dimension the Analytics spending-by-category
-- view groups by.
--
-- Written idempotent and independent of the shared project's current
-- alembic_version state (see supabase_advance_to_0034_widen_alembic_version.sql
-- for why -- nobody running this from outside the Supabase dashboard can
-- verify that marker's real value). Safe to run regardless of whether this
-- has partially run before. Does NOT touch alembic_version itself -- the
-- shared project's alembic_version table currently has more than one row
-- (0024_merge_heads / 0013_card_mock_pan / 0026_credit_card_accounts, seen
-- via SupabaseRestSession on 2026-08-27), an unrelated pre-existing
-- multi-head problem this script deliberately does not attempt to resolve.

BEGIN;

ALTER TABLE budgets DROP COLUMN IF EXISTS category_id;
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS category VARCHAR(50);

COMMIT;
