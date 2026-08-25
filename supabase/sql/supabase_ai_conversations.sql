-- Adds ai_conversations and threads ai_conversation_messages onto it
-- (migration 0031_ai_conversations) — ChatGPT-style multi-conversation
-- history. Every existing message is backfilled into one synthetic
-- "Legacy conversation" per user so no history is lost. See
-- backend/migrations/versions/0031_ai_conversations.py for the source of
-- truth.
--
-- Idempotent: safe to re-run regardless of whether it already applied —
-- the backfill only ever touches rows where conversation_id IS NULL, so a
-- second run finds nothing left to do.
--
-- Run this in the Supabase SQL Editor AFTER
-- supabase_advance_to_0030_fraud_unusual_time.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS ai_conversations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ai_conversations_user_updated ON ai_conversations (user_id, updated_at);

ALTER TABLE ai_conversation_messages ADD COLUMN IF NOT EXISTS conversation_id UUID;

-- Row count before the backfill, for the same before/after check the
-- Python migration does — visible in the SQL Editor's output/notices.
DO $$
DECLARE
    before_count BIGINT;
    after_count BIGINT;
    unassigned_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO before_count FROM ai_conversation_messages;
    RAISE NOTICE 'ai_conversation_messages rows before backfill: %', before_count;

    INSERT INTO ai_conversations (id, user_id, title, created_at, updated_at)
    SELECT gen_random_uuid(), user_id, 'Legacy conversation', MIN(created_at), MAX(created_at)
    FROM ai_conversation_messages
    WHERE conversation_id IS NULL
    GROUP BY user_id;

    UPDATE ai_conversation_messages AS m
    SET conversation_id = c.id
    FROM ai_conversations AS c
    WHERE c.user_id = m.user_id AND c.title = 'Legacy conversation' AND m.conversation_id IS NULL;

    SELECT COUNT(*) INTO unassigned_count FROM ai_conversation_messages WHERE conversation_id IS NULL;
    IF unassigned_count > 0 THEN
        RAISE EXCEPTION 'Backfill left % ai_conversation_messages row(s) without a conversation_id — aborting.', unassigned_count;
    END IF;

    SELECT COUNT(*) INTO after_count FROM ai_conversation_messages;
    RAISE NOTICE 'ai_conversation_messages rows after backfill: % (expected %)', after_count, before_count;
    IF after_count != before_count THEN
        RAISE EXCEPTION 'Row count changed during backfill: % -> %. Aborting.', before_count, after_count;
    END IF;
END $$;

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

UPDATE alembic_version
SET version_num = '0031_ai_conversations'
WHERE version_num = '0030_fraud_unusual_time';

COMMIT;
