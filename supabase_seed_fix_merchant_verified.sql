-- One-off data fix, not a schema migration: the shared Supabase project was
-- seeded (python -m app.seed --supabase-rest) before merchants.verified
-- existed, so the column landed on those 5 rows as its default (false).
-- Marks the same 5 real seed merchants verified=true, matching what
-- backend/app/seed.py sets for a fresh local DB and what was already fixed
-- on each dev's local Postgres.
--
-- Run this in the Supabase SQL Editor AFTER supabase_update_pending.sql.

UPDATE merchants
SET verified = true
WHERE name IN ('Nike', 'Starbucks', 'eMAG', 'OMV', 'Booking.com');
