BEGIN;

-- Running upgrade 0015_transaction_card_id -> 0016_benefit_card_tier_gating

ALTER TABLE reward_benefits ADD COLUMN min_card_tier card_tier;

ALTER TABLE reward_benefits DROP CONSTRAINT reward_benefits_min_tier_id_fkey;

ALTER TABLE reward_benefits DROP COLUMN min_tier_id;

DROP TABLE reward_tiers;

ALTER TABLE benefit_redemptions ADD COLUMN card_id UUID;

ALTER TABLE benefit_redemptions ADD COLUMN redemption_code VARCHAR(20);

UPDATE alembic_version SET version_num='0016_benefit_card_tier_gating' WHERE alembic_version.version_num = '0015_transaction_card_id';

COMMIT;
