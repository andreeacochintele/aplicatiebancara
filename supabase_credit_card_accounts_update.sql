-- Supabase manual update for credit card account balances.
-- Generated for migration:
--   0026_credit_card_accounts
--
-- Safe to run once. This supports credit-card payments by storing credit limit,
-- used balance, available credit inputs, and repayment state per credit card.

BEGIN;

-- Some merged Alembic revision ids are longer than the original 32 chars.
ALTER TABLE alembic_version
    ALTER COLUMN version_num TYPE varchar(128);

CREATE TABLE IF NOT EXISTS credit_card_accounts (
    card_id uuid PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id),
    currency varchar(3) NOT NULL DEFAULT 'RON',
    credit_limit numeric(18, 2) NOT NULL,
    used_amount numeric(18, 2) NOT NULL DEFAULT 0.00,
    annual_interest_rate numeric(5, 2) NOT NULL,
    updated_at timestamptz
);

INSERT INTO credit_card_accounts (
    card_id,
    user_id,
    currency,
    credit_limit,
    used_amount,
    annual_interest_rate,
    updated_at
)
SELECT
    cards.id,
    cards.user_id,
    'RON',
    CASE cards.tier
        WHEN 'PLATINUM' THEN 30000.00
        WHEN 'GOLD' THEN 15000.00
        ELSE 5000.00
    END,
    0.00,
    CASE cards.tier
        WHEN 'PLATINUM' THEN 15.90
        WHEN 'GOLD' THEN 17.50
        ELSE 18.90
    END,
    now()
FROM cards
WHERE cards.type = 'CREDIT'
ON CONFLICT (card_id) DO NOTHING;

DELETE FROM alembic_version
WHERE version_num = '0025_merge_heads';

INSERT INTO alembic_version (version_num)
SELECT '0026_credit_card_accounts'
WHERE NOT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '0026_credit_card_accounts'
);

COMMIT;
