-- Links an assistant ai_conversation_messages row to the ai_agent_actions
-- row it drafted, so the assistant UI can re-render a confirm card with its
-- current status after a conversation is reopened. Additive, nullable.
-- See backend/migrations/versions/0048_conversation_message_action_id.py.
--
-- Idempotent. Run in the Supabase SQL Editor AFTER supabase_agent_actions.sql.

BEGIN;

ALTER TABLE ai_conversation_messages ADD COLUMN IF NOT EXISTS action_id UUID;

UPDATE alembic_version
SET version_num = '0048_conversation_message_action_id'
WHERE version_num = '0047_agent_actions';

COMMIT;
