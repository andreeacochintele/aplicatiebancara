-- Supabase manual update for secured credit card collateral.
-- Generated for migration:
--   0035_credit_card_collateral
--
-- Safe to run once. This lets credit_card_accounts remember which wallet
-- backs a secured credit card and how much money is held as collateral.

BEGIN;

ALTER TABLE alembic_version
    ALTER COLUMN version_num TYPE varchar(255);

ALTER TABLE credit_card_accounts
    ADD COLUMN IF NOT EXISTS collateral_wallet_id uuid REFERENCES wallets(id),
    ADD COLUMN IF NOT EXISTS collateral_amount numeric(18, 2) NOT NULL DEFAULT 0.00;

UPDATE credit_card_accounts
SET collateral_amount = 0.00
WHERE collateral_amount IS NULL;

INSERT INTO alembic_version (version_num)
SELECT '0035_credit_card_collateral'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '0035_credit_card_collateral'
);

COMMIT;
