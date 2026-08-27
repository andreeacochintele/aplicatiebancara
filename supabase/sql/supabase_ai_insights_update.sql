-- Supabase manual update for migration 0038_ai_insights.
--
-- Adds ai_insights: cached, LLM-phrased spending recommendations for the
-- Analytics dashboard's "Spending recommendations" panel. Generated
-- lazily (24h TTL per user, see app/ai/personal_finance/insights.py) -
-- there is no background scheduler in this project.
--
-- Written idempotent and independent of the shared project's current
-- alembic_version state, same reasoning as the other
-- supabase_*_update.sql files landed today. Does NOT touch
-- alembic_version.

BEGIN;

CREATE TABLE IF NOT EXISTS ai_insights (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    message TEXT NOT NULL,
    category VARCHAR(50),
    insight_type VARCHAR(100) NOT NULL,
    dismissed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_ai_insights_user_created ON ai_insights (user_id, created_at);

COMMIT;
