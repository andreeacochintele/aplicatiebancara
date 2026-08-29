-- Supabase manual update for migration 0049_wallet_card_top_up.
--
-- Adds TOP_UP to transaction_type — the wallet "Add money" feature credits
-- a wallet from a user's own mock EasyB card, backed by a real Transaction
-- + WalletLedgerEntry like every other money movement.
--
-- Written idempotent and independent of the shared project's current
-- alembic_version state, same reasoning as
-- supabase_savings_goal_contributions_update.sql. Does NOT touch
-- alembic_version.

BEGIN;

ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'TOP_UP';

COMMIT;
