-- Supabase manual update for credit lifecycle work.
-- Generated for migration:
--   0015_credit_lifecycle
--
-- Run this in Supabase SQL Editor when DATABASE_BACKEND=supabase_rest is used.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'loan_installment_status') THEN
        CREATE TYPE loan_installment_status AS ENUM ('PENDING', 'PAID', 'PARTIAL', 'OVERDUE');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'loan_payment_type') THEN
        CREATE TYPE loan_payment_type AS ENUM ('REGULAR', 'EARLY_REPAYMENT');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'loan_status'
          AND e.enumlabel = 'PAID'
    ) THEN
        ALTER TYPE loan_status ADD VALUE 'PAID';
    END IF;
END $$;

ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS start_date date,
    ADD COLUMN IF NOT EXISTS maturity_date date,
    ADD COLUMN IF NOT EXISTS next_payment_date date;

UPDATE loans
SET start_date = COALESCE(start_date, DATE(created_at)),
    maturity_date = COALESCE(maturity_date, DATE(created_at)),
    next_payment_date = COALESCE(next_payment_date, DATE(created_at));

ALTER TABLE loans
    ALTER COLUMN start_date SET NOT NULL,
    ALTER COLUMN maturity_date SET NOT NULL,
    ALTER COLUMN next_payment_date SET NOT NULL;

CREATE TABLE IF NOT EXISTS loan_installments (
    id uuid PRIMARY KEY,
    loan_id uuid NOT NULL REFERENCES loans(id),
    installment_number integer NOT NULL,
    due_date date NOT NULL,
    payment_amount numeric(18, 2) NOT NULL,
    principal_amount numeric(18, 2) NOT NULL,
    interest_amount numeric(18, 2) NOT NULL,
    fees_amount numeric(18, 2) NOT NULL DEFAULT 0.00,
    remaining_principal numeric(18, 2) NOT NULL,
    status loan_installment_status NOT NULL DEFAULT 'PENDING',
    CONSTRAINT uq_loan_installments_loan_number UNIQUE (loan_id, installment_number)
);

CREATE TABLE IF NOT EXISTS loan_payments (
    id uuid PRIMARY KEY,
    loan_id uuid NOT NULL REFERENCES loans(id),
    transaction_id uuid NULL REFERENCES transactions(id),
    amount numeric(18, 2) NOT NULL,
    principal_paid numeric(18, 2) NOT NULL,
    interest_paid numeric(18, 2) NOT NULL,
    fees_paid numeric(18, 2) NOT NULL DEFAULT 0.00,
    payment_type loan_payment_type NOT NULL,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num varchar(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

DELETE FROM alembic_version
WHERE version_num = '0014_merge_cards_rewards';

INSERT INTO alembic_version (version_num)
SELECT '0015_credit_lifecycle'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '0015_credit_lifecycle'
);

COMMIT;
