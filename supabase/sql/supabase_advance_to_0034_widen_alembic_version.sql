-- Brings the shared Supabase project to migration 0034_widen_alembic_version,
-- REGARDLESS of which of the earlier ad-hoc sync scripts already ran there.
-- Nobody has direct Supabase access from this session to check the real
-- current state, so this is written to be fully idempotent from any prior
-- point rather than assuming a specific starting checkpoint:
--   - Every CREATE TABLE / ADD COLUMN / ADD VALUE is IF NOT EXISTS.
--   - Every backfill UPDATE only touches rows that still need it, so
--     re-running after a partial success is safe.
--   - The final alembic_version write is unconditional (DELETE + INSERT),
--     not the usual "only from known prior state" guard those older sync
--     files use -- by the time this script finishes, the schema genuinely
--     matches 0034, whatever it matched before.
--
-- Covers, in order: 0026_credit_card_accounts, 0028_admin_audit_log,
-- 0029_ai_conversation_messages, 0030_credit_currency_dates,
-- 0030_fraud_unusual_time, 0031_ai_conversations, 0031_credit_documents,
-- 0032_credit_document_content, 0033_merge_heads (no-op),
-- 0034_widen_alembic_version. See the matching files under
-- backend/migrations/versions/ for the source of truth.
--
-- Superseded by this file (safe to ignore, kept for history):
--   supabase_advance_to_0029_ai_conversation_messages.sql
--   supabase_advance_to_0030_fraud_unusual_time.sql
--   supabase_ai_conversations.sql
--   supabase_credit_card_accounts_update.sql
--   supabase_credit_documents_update.sql
-- None of them advanced the version marker all the way to 0030_credit_currency_dates
-- (the credit-currency/loan-dates backfill had no sync script at all until now),
-- which is why none of them are safe to treat as "the" checkpoint on their own.
--
-- Run this in the Supabase SQL Editor.

BEGIN;

-- Widen first: several of the DDL statements below reference revision ids
-- longer than 32 chars indirectly via this same transaction's version bump.
ALTER TABLE alembic_version
    ALTER COLUMN version_num TYPE varchar(255);

-- 0026_credit_card_accounts
CREATE TABLE IF NOT EXISTS credit_card_accounts (
    card_id UUID PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    currency VARCHAR(3) NOT NULL DEFAULT 'RON',
    credit_limit NUMERIC(18, 2) NOT NULL,
    used_amount NUMERIC(18, 2) NOT NULL DEFAULT 0.00,
    annual_interest_rate NUMERIC(5, 2) NOT NULL,
    updated_at TIMESTAMPTZ
);

-- 0028_admin_audit_log
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id UUID PRIMARY KEY,
    admin_user_id UUID NOT NULL REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    old_data JSONB,
    new_data JSONB,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_entity_type ON admin_audit_logs (entity_type);
CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_admin_user_id ON admin_audit_logs (admin_user_id);

-- 0029_ai_conversation_messages
CREATE TABLE IF NOT EXISTS ai_conversation_messages (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    agent_used VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_conversation_messages_user_created ON ai_conversation_messages (user_id, created_at);

-- 0030_credit_currency_dates (backfill; UPDATEs are no-ops once nothing is NULL)
UPDATE credit_applications SET currency = 'RON' WHERE currency IS NULL;
UPDATE loans SET currency = 'RON' WHERE currency IS NULL;
UPDATE loans
SET start_date = COALESCE(start_date, created_at::date, CURRENT_DATE),
    maturity_date = COALESCE(maturity_date, created_at::date, CURRENT_DATE),
    next_payment_date = COALESCE(next_payment_date, created_at::date, CURRENT_DATE)
WHERE start_date IS NULL OR maturity_date IS NULL OR next_payment_date IS NULL;

ALTER TABLE credit_applications ALTER COLUMN currency SET NOT NULL;
ALTER TABLE loans ALTER COLUMN currency SET NOT NULL;
ALTER TABLE loans ALTER COLUMN start_date SET NOT NULL;
ALTER TABLE loans ALTER COLUMN maturity_date SET NOT NULL;
ALTER TABLE loans ALTER COLUMN next_payment_date SET NOT NULL;

-- 0030_fraud_unusual_time
ALTER TYPE fraud_flag_code ADD VALUE IF NOT EXISTS 'UNUSUAL_TIME';

-- 0031_ai_conversations
CREATE TABLE IF NOT EXISTS ai_conversations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ai_conversations_user_updated ON ai_conversations (user_id, updated_at);

ALTER TABLE ai_conversation_messages ADD COLUMN IF NOT EXISTS conversation_id UUID;

-- Only backfills messages that don't have a conversation yet, so re-running
-- this after a partial prior run doesn't create duplicate "Legacy conversation" rows.
INSERT INTO ai_conversations (id, user_id, title, created_at, updated_at)
SELECT gen_random_uuid(), user_id, 'Legacy conversation', MIN(created_at), MAX(created_at)
FROM ai_conversation_messages
WHERE conversation_id IS NULL
GROUP BY user_id
HAVING COUNT(*) > 0;

UPDATE ai_conversation_messages AS m
SET conversation_id = c.id
FROM ai_conversations AS c
WHERE c.user_id = m.user_id AND c.title = 'Legacy conversation' AND m.conversation_id IS NULL;

ALTER TABLE ai_conversation_messages ALTER COLUMN conversation_id SET NOT NULL;

DO $$ BEGIN
    ALTER TABLE ai_conversation_messages
        ADD CONSTRAINT fk_ai_conversation_messages_conversation_id
        FOREIGN KEY (conversation_id) REFERENCES ai_conversations(id);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS ix_ai_conversation_messages_conversation_created
    ON ai_conversation_messages (conversation_id, created_at);

-- 0031_credit_documents + 0032_credit_document_content
DO $$ BEGIN
    CREATE TYPE credit_document_purpose AS ENUM ('CREDIT_SCORE', 'LOAN_APPLICATION');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE credit_document_status AS ENUM ('UPLOADED', 'APPROVED', 'REJECTED', 'NEEDS_MORE_INFO');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS credit_documents (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    application_id UUID REFERENCES credit_applications(id),
    purpose credit_document_purpose NOT NULL,
    document_type VARCHAR(80) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    file_size INTEGER NOT NULL DEFAULT 0,
    content_base64 TEXT,
    status credit_document_status NOT NULL DEFAULT 'UPLOADED',
    evaluation_score INTEGER,
    review_note VARCHAR(500),
    uploaded_at TIMESTAMPTZ NOT NULL,
    reviewed_at TIMESTAMPTZ,
    reviewed_by_admin_id UUID REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_credit_documents_user_id ON credit_documents (user_id);
CREATE INDEX IF NOT EXISTS ix_credit_documents_application_id ON credit_documents (application_id);
CREATE INDEX IF NOT EXISTS ix_credit_documents_status ON credit_documents (status);
CREATE INDEX IF NOT EXISTS ix_credit_documents_purpose ON credit_documents (purpose);

-- 0033_merge_heads / 0034_widen_alembic_version: schema now matches this
-- state regardless of which prior checkpoint the row was actually at.
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('0034_widen_alembic_version');

COMMIT;
