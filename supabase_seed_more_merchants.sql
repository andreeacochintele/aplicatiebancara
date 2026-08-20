-- One-off data addition, not a schema migration: adds 5 more demo merchants
-- beyond architecture.md's original Nike/Starbucks/eMAG/OMV/Booking.com
-- example line-up, including a first Entertainment-category merchant.
-- Mirrors what's also added to backend/app/seed.py (both the local
-- SQLAlchemy seed and the Supabase REST seed) so a fresh database gets the
-- same catalog — this script is only for a shared DB that was already
-- seeded before this change.
--
-- Idempotent: merchant names aren't unique-constrained, so a plain INSERT
-- would create duplicates on a second run. This only inserts the ones not
-- already present by name, so it's safe to re-run regardless of whether it
-- (or a partial version of it) already ran.

WITH desired(name, category) AS (
  VALUES
    ('Zara', 'Retail'),
    ('KFC', 'Food'),
    ('Petrom', 'Fuel'),
    ('Emirates', 'Travel'),
    ('Cinema City', 'Entertainment')
),
new_merchants AS (
  INSERT INTO merchants (id, name, category, status, verified, created_at)
  SELECT gen_random_uuid(), desired.name, desired.category, 'ACTIVE', true, now()
  FROM desired
  WHERE NOT EXISTS (SELECT 1 FROM merchants WHERE merchants.name = desired.name)
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
