-- One-off data addition, not a schema migration: adds 5 more redeemable
-- benefits beyond the original 5 (Priority Pass lounge, eMAG/Starbucks
-- discounts, free airport transfer, travel insurance), spreading across all
-- five BenefitCategory values and card tiers so the catalog has more than
-- one option per category/tier. Mirrors what's also added to
-- backend/app/seed.py (both the local SQLAlchemy seed and the Supabase REST
-- seed) so a fresh database gets the same catalog — this script is only for
-- a shared DB that was already seeded before this change.
--
-- Idempotent: only inserts benefits not already present by name, so it's
-- safe to re-run regardless of whether it already ran.
--
-- Run this in the Supabase SQL Editor AFTER supabase_update_pending.sql
-- (min_card_tier must exist on reward_benefits first).

INSERT INTO reward_benefits (id, name, category, description, points_cost, min_card_tier, partner_name, status, created_at)
SELECT * FROM (
  VALUES
    (gen_random_uuid(), '20% off at Zara', 'RETAIL_DISCOUNT'::benefit_category, '20% discount voucher for your next Zara order.', 500, NULL::card_tier, 'Zara', 'ACTIVE'::benefit_status, now()),
    (gen_random_uuid(), '2 free tickets at Cinema City', 'OTHER'::benefit_category, 'Two complimentary tickets for any screening at Cinema City.', 400, NULL::card_tier, 'Cinema City', 'ACTIVE'::benefit_status, now()),
    (gen_random_uuid(), 'Extra baggage allowance (+10kg)', 'TRAVEL'::benefit_category, 'An extra 10kg of checked baggage on your next Emirates flight.', 700, 'GOLD'::card_tier, 'Emirates', 'ACTIVE'::benefit_status, now()),
    (gen_random_uuid(), 'Airport spa access', 'LOUNGE_ACCESS'::benefit_category, 'One complimentary spa session at a partner airport lounge.', 1200, 'GOLD'::card_tier, 'Priority Pass', 'ACTIVE'::benefit_status, now()),
    (gen_random_uuid(), 'Purchase protection insurance (30 days)', 'INSURANCE'::benefit_category, '30 days of purchase protection coverage for a new purchase.', 650, 'PLATINUM'::card_tier, 'Allianz', 'ACTIVE'::benefit_status, now())
) AS new_benefits(id, name, category, description, points_cost, min_card_tier, partner_name, status, created_at)
WHERE NOT EXISTS (SELECT 1 FROM reward_benefits WHERE reward_benefits.name = new_benefits.name);
