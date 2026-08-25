-- Catches the shared Supabase schema up from 0026_fraud_cases (the last
-- checkpoint any supabase/sql/*.sql file reached) to 0030_fraud_unusual_time,
-- covering four migrations that never got a Supabase SQL counterpart:
--   0026_credit_card_accounts  -- credit_card_accounts table (parallel
--                                 branch to 0026_fraud_cases, merged at
--                                 0027_merge_heads)
--   0027_merge_heads           -- no-op merge of the two 0026 branches
--   0028_admin_audit_log       -- admin_audit_logs table
--   0029_ai_conversation_messages -- orchestrator short-term chat history
--   0030_fraud_unusual_time    -- adds UNUSUAL_TIME to fraud_flag_code
-- See backend/migrations/versions/<name>.py for each one's source of truth.
--
-- Idempotent: safe to re-run regardless of whether it already applied.
-- Prerequisite: supabase_fraud_cases.sql must already be applied (this
-- file's version guard only fires from that exact checkpoint).

BEGIN;

CREATE TABLE IF NOT EXISTS credit_card_accounts (
    card_id UUID PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    currency VARCHAR(3) NOT NULL DEFAULT 'RON',
    credit_limit NUMERIC(18, 2) NOT NULL,
    used_amount NUMERIC(18, 2) NOT NULL DEFAULT '0.00',
    annual_interest_rate NUMERIC(5, 2) NOT NULL,
    updated_at TIMESTAMPTZ
);

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

CREATE TABLE IF NOT EXISTS ai_conversation_messages (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    agent_used VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ai_conversation_messages_user_created
    ON ai_conversation_messages (user_id, created_at);

ALTER TYPE fraud_flag_code ADD VALUE IF NOT EXISTS 'UNUSUAL_TIME';

-- Only fires from the known pre-0030 checkpoint, so it can't regress a
-- database that's already past this point (same idempotency style as
-- supabase_fraud_cases.sql / supabase_advance_to_0025_merge_heads.sql).
UPDATE alembic_version
SET version_num = '0030_fraud_unusual_time'
WHERE version_num = '0026_fraud_cases';

COMMIT;
