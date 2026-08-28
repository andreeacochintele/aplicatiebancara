-- Supabase manual update for migration 0040_identity_documents.
--
-- Onboarding step 3: identity_documents table (ID card upload + MRZ
-- extraction + admin review) and new kyc_document_status values
-- (VERIFIED, NEEDS_REVIEW, APPROVED, REJECTED) plus the new
-- mrz_format_code enum (TD1, TD2). See
-- backend/migrations/versions/0040_identity_documents.py for the source
-- of truth.
--
-- Idempotent: safe to re-run regardless of whether it already applied.
--
-- This migration branches off 0039_ai_insights_currency, one of THREE
-- alembic heads that already existed on master before this branch was
-- created (0036_card_pin_hash and 0037_wallet_iban are the other two,
-- neither reconciled yet — see the migration file's own note). The final
-- UPDATE below only advances the 0039 branch's alembic_version row; it
-- does not attempt to resolve the pre-existing 3-way split. If your
-- Supabase project's alembic_version is instead sitting on
-- 0036_card_pin_hash or 0037_wallet_iban, this UPDATE simply won't match
-- and won't fire — run whichever of those branches' own catch-up SQL
-- applies first, then this one.

BEGIN;

ALTER TYPE kyc_document_status ADD VALUE IF NOT EXISTS 'VERIFIED';
ALTER TYPE kyc_document_status ADD VALUE IF NOT EXISTS 'NEEDS_REVIEW';
ALTER TYPE kyc_document_status ADD VALUE IF NOT EXISTS 'APPROVED';
ALTER TYPE kyc_document_status ADD VALUE IF NOT EXISTS 'REJECTED';

DO $$ BEGIN
    CREATE TYPE mrz_format_code AS ENUM ('TD1', 'TD2');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS identity_documents (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES users(id),
    front_image_base64 TEXT,
    back_image_base64 TEXT,
    detected_format mrz_format_code,
    extracted_surname VARCHAR(100),
    extracted_given_names VARCHAR(100),
    extracted_cnp VARCHAR(13),
    extracted_date_of_birth DATE,
    extracted_date_of_expiry DATE,
    mrz_checks_passed BOOLEAN NOT NULL DEFAULT FALSE,
    cross_check_passed BOOLEAN NOT NULL DEFAULT FALSE,
    failure_reason VARCHAR(255),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    status kyc_document_status NOT NULL DEFAULT 'NOT_STARTED',
    review_note VARCHAR(500),
    reviewed_by_admin_id UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_identity_documents_user_id ON identity_documents (user_id);

-- Only fires from the known pre-0040 state on this branch of the head
-- split, so it can't regress a database already past this point (same
-- idempotency guard style as supabase_fraud_cases.sql).
UPDATE alembic_version
SET version_num = '0040_identity_documents'
WHERE version_num = '0039_ai_insights_currency';

COMMIT;
