-- Adds ai_agent_actions — a drafted, confirm-pending banking action from the
-- Actions Agent (ai/actions/), plus its lifecycle-status enum. Feature-local:
-- one table, one enum, nothing else touched. See
-- backend/migrations/versions/0047_agent_actions.py for the source of truth.
--
-- Idempotent: safe to re-run (CREATE ... IF NOT EXISTS, guarded enum create).
--
-- Run this in the Supabase SQL Editor AFTER supabase_identity_documents.sql
-- (i.e. once alembic_version has reached 0046_merge_heads).

BEGIN;

DO $$ BEGIN
    CREATE TYPE ai_agent_action_status AS ENUM (
        'DRAFT', 'CONFIRMED', 'EXECUTED', 'EXPIRED',
        'CANCELLED', 'FAILED', 'SUPERSEDED', 'NEEDS_REVIEW'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS ai_agent_actions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    conversation_id UUID REFERENCES ai_conversations(id),
    type VARCHAR(50) NOT NULL,
    status ai_agent_action_status NOT NULL DEFAULT 'DRAFT',
    payload JSONB NOT NULL,
    result_transaction_id UUID,
    idempotency_key VARCHAR(64),
    error_code VARCHAR(64),
    error_detail VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    CONSTRAINT uq_ai_agent_actions_idempotency_key UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_ai_agent_actions_user_created ON ai_agent_actions (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_ai_agent_actions_conversation ON ai_agent_actions (conversation_id);

UPDATE alembic_version
SET version_num = '0047_agent_actions'
WHERE version_num = '0046_merge_heads';

COMMIT;
