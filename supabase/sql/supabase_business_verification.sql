-- Adds business KYB verification: business_profiles gets a
-- verification_status (PENDING_VERIFICATION/VERIFIED/REJECTED) plus
-- who/when decided it, and a new business_documents table holds the
-- proof-of-company uploads an admin reviews. See
-- backend/migrations/versions/0058_business_verification.py for the
-- source of truth.
--
-- URGENT: BusinessProfilePublic now requires verification_status on every
-- row, so until this script runs, GET /business/profile(s) fails live
-- (Postgres 42703 "column does not exist") and existing companies become
-- invisible in the app — this is not data loss, the rows are untouched.
--
-- Idempotent: safe to re-run.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'business_verification_status') THEN
        CREATE TYPE business_verification_status AS ENUM ('PENDING_VERIFICATION', 'VERIFIED', 'REJECTED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'business_document_type') THEN
        CREATE TYPE business_document_type AS ENUM (
            'REGISTRATION_CERTIFICATE', 'ARTICLES_OF_ASSOCIATION', 'LEGAL_REPRESENTATIVE_ID', 'PROOF_OF_ADDRESS'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'business_document_status') THEN
        CREATE TYPE business_document_status AS ENUM ('UPLOADED', 'APPROVED', 'REJECTED');
    END IF;
END $$;

ALTER TABLE business_profiles
    ADD COLUMN IF NOT EXISTS verification_status business_verification_status NOT NULL DEFAULT 'PENDING_VERIFICATION';
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS verified_at timestamptz;
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS verified_by_admin_id uuid REFERENCES users(id);
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS rejection_reason varchar(500);

CREATE TABLE IF NOT EXISTS business_documents (
    id UUID PRIMARY KEY,
    business_profile_id UUID NOT NULL REFERENCES business_profiles(id),
    user_id UUID NOT NULL REFERENCES users(id),
    document_type business_document_type NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    file_size INTEGER NOT NULL DEFAULT 0,
    content_base64 TEXT,
    status business_document_status NOT NULL DEFAULT 'UPLOADED',
    review_note VARCHAR(500),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by_admin_id UUID REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_business_documents_business_profile_id ON business_documents (business_profile_id);
CREATE INDEX IF NOT EXISTS ix_business_documents_user_id ON business_documents (user_id);

UPDATE alembic_version
SET version_num = '0058_business_verification'
WHERE version_num IN ('0054_ai_insight_period_key', '0055_payment_request_reference', '0056_bulk_transfer_templates', '0057_merge_heads');

COMMIT;
