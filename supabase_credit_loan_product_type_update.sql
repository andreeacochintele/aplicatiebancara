-- Supabase manual update for loan product types on credit applications.
-- Generated for migration:
--   0020_credit_loan_product_type
--
-- Run this in Supabase SQL Editor when DATABASE_BACKEND=supabase_rest is used.

BEGIN;

DO $$
BEGIN
    CREATE TYPE loan_product_type AS ENUM (
        'PERSONAL_LOAN',
        'MORTGAGE',
        'AUTO_LOAN',
        'STUDENT_LOAN',
        'HOME_IMPROVEMENT',
        'DEBT_CONSOLIDATION'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE credit_applications
    ADD COLUMN IF NOT EXISTS loan_product_type loan_product_type;

UPDATE credit_applications
SET loan_product_type = 'PERSONAL_LOAN'
WHERE type = 'PERSONAL_LOAN'
  AND loan_product_type IS NULL;

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num varchar(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

DELETE FROM alembic_version
WHERE version_num = '0019_credit_profile_currency';

INSERT INTO alembic_version (version_num)
SELECT '0020_credit_loan_product_type'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '0020_credit_loan_product_type'
);

COMMIT;
