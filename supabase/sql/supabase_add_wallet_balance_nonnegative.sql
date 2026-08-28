-- Mirrors migration 0042_wallet_balance_nonnegative: adds CHECK constraints
-- so a wallet's balances can never go negative at the DB level — a backstop
-- behind the SELECT ... FOR UPDATE row locking added in
-- backend/app/transactions/service.py, not a replacement for it.
--
-- Idempotent: safe to re-run (skips if the constraint already exists).
--
-- Run this in the Supabase SQL Editor.

BEGIN;

DO $$ BEGIN
    ALTER TABLE wallets ADD CONSTRAINT ck_wallets_available_balance_nonnegative CHECK (available_balance >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE wallets ADD CONSTRAINT ck_wallets_reserved_balance_nonnegative CHECK (reserved_balance >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

COMMIT;
