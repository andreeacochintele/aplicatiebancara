-- Supabase manual update for migration 0039_ai_insights_currency.
--
-- Adds ai_insights.currency - every comparison in
-- AnalyticsService.spending_recommendations() is scoped to one currency
-- at a time, so an insight about a category is really about that
-- category in one currency. Surfaces it explicitly in the UI instead of
-- only implying it in the LLM-phrased message text, which made a
-- EUR-scoped share-of-total look like it contradicted a RON-scoped chart
-- on the same dashboard.
--
-- Written idempotent, same reasoning as the other supabase_*_update.sql
-- files landed today. Does NOT touch alembic_version.

BEGIN;

ALTER TABLE ai_insights ADD COLUMN IF NOT EXISTS currency VARCHAR(3);

COMMIT;
