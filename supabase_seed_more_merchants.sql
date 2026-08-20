-- One-off data addition, not a schema migration: adds 5 more demo merchants
-- beyond architecture.md's original Nike/Starbucks/eMAG/OMV/Booking.com
-- example line-up, including a first Entertainment-category merchant.
-- Mirrors what's also added to backend/app/seed.py (both the local
-- SQLAlchemy seed and the Supabase REST seed) so a fresh database gets the
-- same catalog — this script is only for a shared DB that was already
-- seeded before this change.
--
-- Safe to run once; merchant names aren't unique-constrained, so re-running
-- would create duplicates. Check `SELECT name FROM merchants` first if
-- unsure whether this already ran.

WITH new_merchants AS (
  INSERT INTO merchants (id, name, category, status, verified, created_at)
  VALUES
    (gen_random_uuid(), 'Zara', 'Retail', 'ACTIVE', true, now()),
    (gen_random_uuid(), 'KFC', 'Food', 'ACTIVE', true, now()),
    (gen_random_uuid(), 'Petrom', 'Fuel', 'ACTIVE', true, now()),
    (gen_random_uuid(), 'Emirates', 'Travel', 'ACTIVE', true, now()),
    (gen_random_uuid(), 'Cinema City', 'Entertainment', 'ACTIVE', true, now())
  RETURNING id, name
)
INSERT INTO cashback_offers (id, merchant_id, cashback_percent, start_date, end_date, status, created_at)
SELECT
  gen_random_uuid(),
  new_merchants.id,
  CASE new_merchants.name
    WHEN 'Zara' THEN 6
    WHEN 'KFC' THEN 8
    WHEN 'Petrom' THEN 4
    WHEN 'Emirates' THEN 5
    WHEN 'Cinema City' THEN 12
  END,
  current_date - interval '1 day',
  current_date + interval '335 days',
  'ACTIVE',
  now()
FROM new_merchants;
