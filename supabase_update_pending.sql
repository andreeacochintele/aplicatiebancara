-- Everything from our own migration chain that Supabase is still missing:
-- 0016_benefit_card_tier_gating (min_card_tier gating, redemption receipts)
-- + 0019_referral_and_proof_codes (referral/purchase codes)
-- + 0020_redemption_expiry (voucher expiry/used tracking). 0017 and 0018
-- belong to other branches (Credit, Payments) or are no-op merge markers —
-- see team_supabase_workflow.md for their own scripts. This jumps the
-- version marker straight from our last-known Supabase state to our real
-- final tip since there's no DDL of ours in between.
--
-- Safe to run on its own regardless of whether Credit/Payments' scripts
-- have been applied yet — this only touches reward_benefits,
-- benefit_redemptions, reward_accounts and reward_transactions.

BEGIN;

-- 0016_benefit_card_tier_gating

ALTER TABLE reward_benefits ADD COLUMN min_card_tier card_tier;

ALTER TABLE reward_benefits DROP CONSTRAINT reward_benefits_min_tier_id_fkey;

ALTER TABLE reward_benefits DROP COLUMN min_tier_id;

DROP TABLE reward_tiers;

ALTER TABLE benefit_redemptions ADD COLUMN card_id UUID;

ALTER TABLE benefit_redemptions ADD COLUMN redemption_code VARCHAR(20);

-- 0019_referral_and_proof_codes

ALTER TABLE reward_accounts ADD COLUMN referral_code VARCHAR(20);

ALTER TABLE reward_accounts ADD CONSTRAINT uq_reward_accounts_referral_code UNIQUE (referral_code);

ALTER TABLE reward_transactions ADD COLUMN proof_code VARCHAR(20);

-- 0020_redemption_expiry

ALTER TABLE benefit_redemptions ADD COLUMN expires_at TIMESTAMPTZ;
ALTER TABLE benefit_redemptions ADD COLUMN used_at TIMESTAMPTZ;

UPDATE alembic_version SET version_num='0020_redemption_expiry' WHERE alembic_version.version_num = '0015_transaction_card_id';

COMMIT;
