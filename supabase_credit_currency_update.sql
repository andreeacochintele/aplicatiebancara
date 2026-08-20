-- Supabase manual update for credit currency support.
-- Generated for migration:
--   0017_credit_currency
--
-- Run this in Supabase SQL Editor when DATABASE_BACKEND=supabase_rest is used.

BEGIN;

ALTER TABLE credit_applications
    ADD COLUMN IF NOT EXISTS currency varchar(3);

ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS currency varchar(3);

UPDATE credit_applications
SET currency = 'RON'
WHERE currency IS NULL;

UPDATE loans
SET currency = 'RON'
WHERE currency IS NULL;

ALTER TABLE credit_applications
    ALTER COLUMN currency SET NOT NULL;

ALTER TABLE loans
    ALTER COLUMN currency SET NOT NULL;

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num varchar(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

DELETE FROM alembic_version
WHERE version_num = '0016_card_preferences_cascade';

INSERT INTO alembic_version (version_num)
SELECT '0017_credit_currency'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '0017_credit_currency'
);

COMMIT;
