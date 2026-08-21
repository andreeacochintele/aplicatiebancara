-- Everything from our own migration chain that Supabase is still missing:
-- 0016_benefit_card_tier_gating (min_card_tier gating, redemption receipts)
-- + 0019_referral_and_proof_codes (referral/purchase codes)
-- + 0020_redemption_expiry (voucher expiry/used tracking). 0017 and 0018
-- belong to other branches (Credit, Payments) or are no-op merge markers —
-- see team_supabase_workflow.md for their own scripts. This jumps the
-- version marker straight from our last-known Supabase state to our real
-- final tip since there's no DDL of ours in between.
--
-- Idempotent on purpose: an earlier draft of this same file (without the
-- 0020 section) already got run here once, so plain ALTER TABLE ADD COLUMN
-- failed on "min_card_tier already exists" and aborted the whole
-- transaction before ever reaching expires_at/used_at further down. Every
-- statement below is safe to re-run regardless of how much of this has
-- already been applied.
--
-- Safe to run on its own regardless of whether Credit/Payments' scripts
-- have been applied yet — this only touches reward_benefits,
-- benefit_redemptions, reward_accounts and reward_transactions.

BEGIN;

-- 0016_benefit_card_tier_gating

ALTER TABLE reward_benefits ADD COLUMN IF NOT EXISTS min_card_tier card_tier;

ALTER TABLE reward_benefits DROP CONSTRAINT IF EXISTS reward_benefits_min_tier_id_fkey;

ALTER TABLE reward_benefits DROP COLUMN IF EXISTS min_tier_id;

DROP TABLE IF EXISTS reward_tiers;

ALTER TABLE benefit_redemptions ADD COLUMN IF NOT EXISTS card_id UUID;

ALTER TABLE benefit_redemptions ADD COLUMN IF NOT EXISTS redemption_code VARCHAR(20);

-- 0019_referral_and_proof_codes

ALTER TABLE reward_accounts ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20);

-- ADD CONSTRAINT has no IF NOT EXISTS in Postgres, so guard it manually.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_reward_accounts_referral_code'
  ) THEN
    ALTER TABLE reward_accounts ADD CONSTRAINT uq_reward_accounts_referral_code UNIQUE (referral_code);
  END IF;
END $$;

ALTER TABLE reward_transactions ADD COLUMN IF NOT EXISTS proof_code VARCHAR(20);

-- 0020_redemption_expiry

ALTER TABLE benefit_redemptions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE benefit_redemptions ADD COLUMN IF NOT EXISTS used_at TIMESTAMPTZ;

-- Only advances the marker from one of this branch's own known pre-0020
-- states — never overwrites blindly, so it can't regress a database that's
-- already at 0020+ or that another branch's migration has moved elsewhere.
UPDATE alembic_version
SET version_num = '0020_redemption_expiry'
WHERE version_num IN (
  '0015_transaction_card_id',
  '0016_benefit_card_tier_gating',
  '0018_merge_heads',
  '0019_referral_and_proof_codes'
);

COMMIT;
