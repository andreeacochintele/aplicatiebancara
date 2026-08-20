-- One-off data fix, not a schema migration: the shared Supabase project's
-- reward_benefits rows were seeded before min_card_tier existed (their old
-- min_tier_id gating just got dropped by supabase_update_pending.sql), so
-- they'd otherwise sit ungated — redeemable by anyone regardless of card.
-- Backfills the same mapping backend/app/seed.py uses for a fresh database.
--
-- Run this in the Supabase SQL Editor AFTER supabase_update_pending.sql.

UPDATE reward_benefits
SET min_card_tier = 'GOLD'
WHERE name IN ('Priority Pass Lounge Access', 'Free airport transfer');

UPDATE reward_benefits
SET min_card_tier = 'PLATINUM'
WHERE name = 'Travel insurance (7 days)';
