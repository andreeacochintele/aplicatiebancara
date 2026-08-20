-- Supabase manual update for card preference cascade.
-- Generated for migration:
--   0016_card_preferences_cascade
--
-- Run this in Supabase SQL Editor when DATABASE_BACKEND=supabase_rest is used.

BEGIN;

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
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE card_payment_preferences DROP CONSTRAINT %I', constraint_name);
    END IF;

    ALTER TABLE card_payment_preferences
        ADD CONSTRAINT card_payment_preferences_card_id_fkey
        FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE;
END $$;

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num varchar(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

DELETE FROM alembic_version
WHERE version_num = '0015_credit_lifecycle';

INSERT INTO alembic_version (version_num)
SELECT '0016_card_preferences_cascade'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '0016_card_preferences_cascade'
);

COMMIT;
