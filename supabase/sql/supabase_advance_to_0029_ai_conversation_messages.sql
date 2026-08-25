-- Brings the shared Supabase project up to migration 0029_ai_conversation_messages.
-- Three tables landed since the last sync and were never applied here:
--   0026_credit_card_accounts — stored credit card accounts
--   0028_admin_audit_log      — admin_audit_logs (architecture.md §27/§34)
--   0029_ai_conversation_messages — orchestrator's short-term chat history
-- (0027_merge_heads is a no-op merge migration, no DDL of its own.)
--
-- See the matching files under backend/migrations/versions/ for the source
-- of truth. Idempotent: every CREATE is IF NOT EXISTS, and the final
-- alembic_version UPDATE only fires from a known pre-0029 state, so this is
-- safe to re-run regardless of what's already applied.
--
-- Run this in the Supabase SQL Editor.

BEGIN;

CREATE TABLE IF NOT EXISTS credit_card_accounts (
    card_id UUID PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    currency VARCHAR(3) NOT NULL DEFAULT 'RON',
    credit_limit NUMERIC(18, 2) NOT NULL,
    used_amount NUMERIC(18, 2) NOT NULL DEFAULT 0.00,
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

CREATE INDEX IF NOT EXISTS ix_ai_conversation_messages_user_created ON ai_conversation_messages (user_id, created_at);

-- Only fires from a known pre-0029 state, so it can't regress a database
-- that's already past this point (same idempotency guard style as the
-- earlier supabase_advance_to_0025_merge_heads.sql / supabase_fraud_cases.sql).
UPDATE alembic_version
SET version_num = '0029_ai_conversation_messages'
WHERE version_num IN (
    '0025_merge_heads',
    '0026_credit_card_accounts',
    '0026_fraud_cases',
    '0027_merge_heads',
    '0028_admin_audit_log'
);

COMMIT;
