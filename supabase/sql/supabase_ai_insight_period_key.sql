-- ai_insights.period_key — scopes spending-recommendation caching per
-- calendar month ("YYYY-MM"), not just per user, so a past month's
-- recommendations can be cached forever while the real current month
-- keeps its short TTL. See backend/migrations/versions/0054_ai_insight_period_key.py.
--
-- Idempotent — safe to run regardless of prior state. Backfills every
-- pre-existing row from its own created_at, same as the Alembic migration.
--
-- Deliberately does NOT touch alembic_version — see
-- supabase_card_freeze_reason.sql's header for why (unresolved multi-head
-- tracking problem, unrelated to this change).

BEGIN;

ALTER TABLE ai_insights ADD COLUMN IF NOT EXISTS period_key varchar(7);

UPDATE ai_insights SET period_key = to_char(created_at, 'YYYY-MM') WHERE period_key IS NULL;

ALTER TABLE ai_insights ALTER COLUMN period_key SET NOT NULL;

DROP INDEX IF EXISTS ix_ai_insights_user_created;
CREATE INDEX IF NOT EXISTS ix_ai_insights_user_period_created ON ai_insights (user_id, period_key, created_at);

COMMIT;
