-- Adds bulk_transfer_templates / bulk_transfer_template_rows — a saved
-- payroll-style batch the owner can re-run on demand and advance on a
-- schedule. Reuses the existing scheduled_payment_frequency /
-- scheduled_payment_status enum types (created by the ScheduledPayment
-- migrations) rather than creating new ones. See
-- backend/migrations/versions/0056_bulk_transfer_templates.py for the
-- source of truth.
--
-- Idempotent: safe to re-run (CREATE ... IF NOT EXISTS).
--
-- Run this in the Supabase SQL Editor once alembic_version has reached
-- 0055_transaction_batch_reference (this repo's canonical 0055 — the
-- payment_requests.reference/note branch has its own separate 0055 and
-- needs its own reconciliation, see that migration's docstring).

BEGIN;

CREATE TABLE IF NOT EXISTS bulk_transfer_templates (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL REFERENCES users(id),
    source_wallet_id UUID NOT NULL REFERENCES wallets(id),
    name VARCHAR(100) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    frequency scheduled_payment_frequency NOT NULL,
    next_run_on DATE NOT NULL,
    status scheduled_payment_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bulk_transfer_templates_owner ON bulk_transfer_templates (owner_user_id);

CREATE TABLE IF NOT EXISTS bulk_transfer_template_rows (
    id UUID PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES bulk_transfer_templates(id),
    beneficiary_name VARCHAR(255) NOT NULL,
    iban VARCHAR(34) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bulk_transfer_template_rows_template ON bulk_transfer_template_rows (template_id);

UPDATE alembic_version
SET version_num = '0056_bulk_transfer_templates'
WHERE version_num = '0055_transaction_batch_reference';

COMMIT;
