-- One-off cleanup: an earlier (non-idempotent) run of
-- supabase_seed_more_merchants.sql got applied more than once before it was
-- fixed to be re-run-safe, leaving duplicate rows for the 5 merchants it
-- adds (Zara, KFC, Petrom, Emirates, Cinema City) — same name, different
-- ids, each with its own cashback_offers row.
--
-- Keeps the oldest row per name as the survivor, reassigns anything that
-- points at a duplicate (transactions.merchant_id has no FK constraint but
-- would still go stale) to the survivor, then removes the duplicates' own
-- cashback_offers and the duplicate merchant rows themselves.
--
-- Safe to re-run: once there's only one row per name, both DELETEs affect
-- 0 rows.

BEGIN;

CREATE TEMP TABLE merchant_dupes AS
SELECT
  id AS dup_id,
  first_value(id) OVER (PARTITION BY name ORDER BY created_at ASC, id ASC) AS survivor_id
FROM merchants
WHERE name IN ('Zara', 'KFC', 'Petrom', 'Emirates', 'Cinema City');

DELETE FROM merchant_dupes WHERE dup_id = survivor_id;

UPDATE transactions
SET merchant_id = merchant_dupes.survivor_id
FROM merchant_dupes
WHERE transactions.merchant_id = merchant_dupes.dup_id;

DELETE FROM cashback_offers WHERE merchant_id IN (SELECT dup_id FROM merchant_dupes);

DELETE FROM merchants WHERE id IN (SELECT dup_id FROM merchant_dupes);

DROP TABLE merchant_dupes;

COMMIT;
