-- Supabase manual update for cards work.
-- Generated for migrations:
--   0011_card_tiers
--   0012_card_mock_cvv
--   0013_card_mock_pan
--   0014_merge_cards_rewards (marker only when rewards branch is also present)
--
-- Safe to run once. Uses IF NOT EXISTS / catalog checks where PostgreSQL needs it.
-- This is sandbox/demo card data only. mock_pan and mock_cvv are not real card credentials.

BEGIN;

-- Make card deletes safe when preferences already exist.
-- The original FK did not specify ON DELETE CASCADE.
DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT conname
    INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'card_payment_preferences'::regclass
      AND confrelid = 'cards'::regclass
      AND contype = 'f'
      AND conkey = ARRAY[
          (
              SELECT attnum
              FROM pg_attribute
              WHERE attrelid = 'card_payment_preferences'::regclass
                AND attname = 'card_id'
          )
      ]::smallint[]
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE card_payment_preferences DROP CONSTRAINT %I', constraint_name);
    END IF;

    ALTER TABLE card_payment_preferences
        ADD CONSTRAINT card_payment_preferences_card_id_fkey
        FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE;
END $$;

-- 0011_card_tiers: enum + cards.tier
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'card_tier') THEN
        CREATE TYPE card_tier AS ENUM ('REGULAR', 'GOLD', 'PLATINUM');
    END IF;
END $$;

ALTER TABLE cards
    ADD COLUMN IF NOT EXISTS tier card_tier;

UPDATE cards
SET tier = 'REGULAR'
WHERE type IN ('DEBIT', 'CREDIT')
  AND tier IS NULL;

-- 0012_card_mock_cvv: sandbox-only mock CVV
ALTER TABLE cards
    ADD COLUMN IF NOT EXISTS mock_cvv varchar(3);

UPDATE cards
SET mock_cvv = lpad((floor(random() * 1000))::int::text, 3, '0')
WHERE mock_cvv IS NULL;

ALTER TABLE cards
    ALTER COLUMN mock_cvv SET NOT NULL;

-- 0013_card_mock_pan: sandbox-only mock full card number for reveal UI
ALTER TABLE cards
    ADD COLUMN IF NOT EXISTS mock_pan varchar(19);

UPDATE cards
SET mock_pan =
    '4000 '
    || lpad((floor(random() * 10000))::int::text, 4, '0')
    || ' '
    || lpad((floor(random() * 10000))::int::text, 4, '0')
    || ' '
    || last_four
WHERE mock_pan IS NULL;

ALTER TABLE cards
    ALTER COLUMN mock_pan SET NOT NULL;

-- Alembic bookkeeping.
-- The cards branch head after these schema changes is 0013_card_mock_pan.
-- If the rewards/merchants branch head 0012_merchant_verified is also present,
-- replace both branch heads with merge head 0014_merge_cards_rewards.
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num varchar(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

DELETE FROM alembic_version
WHERE version_num IN ('0010_merge_rewards', '0011_card_tiers', '0012_card_mock_cvv');

INSERT INTO alembic_version (version_num)
SELECT '0013_card_mock_pan'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version
    WHERE version_num IN ('0013_card_mock_pan', '0014_merge_cards_rewards')
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM alembic_version WHERE version_num = '0012_merchant_verified')
       AND EXISTS (SELECT 1 FROM alembic_version WHERE version_num = '0013_card_mock_pan') THEN
        DELETE FROM alembic_version
        WHERE version_num IN ('0012_merchant_verified', '0013_card_mock_pan');

        INSERT INTO alembic_version (version_num)
        SELECT '0014_merge_cards_rewards'
        WHERE NOT EXISTS (
            SELECT 1 FROM alembic_version WHERE version_num = '0014_merge_cards_rewards'
        );
    END IF;
END $$;

COMMIT;
