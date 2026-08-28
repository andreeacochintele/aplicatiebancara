-- Allows a user to hold more than one wallet in the same currency
-- (migration 0045_wallet_nickname_multi_currency): drops
-- UNIQUE(user_id, currency) and adds a nickname column so same-currency
-- wallets can be told apart in the UI.
--
-- Idempotent: safe to re-run.
--
-- Run this in the Supabase SQL Editor.

BEGIN;

ALTER TABLE wallets DROP CONSTRAINT IF EXISTS uq_wallet_user_currency;
ALTER TABLE wallets ADD COLUMN IF NOT EXISTS nickname VARCHAR(50);

COMMIT;
