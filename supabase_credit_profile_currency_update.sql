-- Supabase manual update for credit profile currency support.
-- Generated for migration:
--   0019_credit_profile_currency
--
-- Run this in Supabase SQL Editor when DATABASE_BACKEND=supabase_rest is used.

BEGIN;

ALTER TABLE credit_profiles
    ADD COLUMN IF NOT EXISTS currency varchar(3);

UPDATE credit_profiles
SET currency = 'RON'
WHERE currency IS NULL;

ALTER TABLE credit_profiles
    ALTER COLUMN currency SET NOT NULL;

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num varchar(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

DELETE FROM alembic_version
WHERE version_num = '0018_merge_payments_credit';

INSERT INTO alembic_version (version_num)
SELECT '0019_credit_profile_currency'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '0019_credit_profile_currency'
);

COMMIT;
