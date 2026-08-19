BEGIN;

-- Running upgrade 0014_merge_cards_rewards -> 0015_transaction_card_id

ALTER TABLE transactions ADD COLUMN card_id UUID;

UPDATE alembic_version SET version_num='0015_transaction_card_id' WHERE alembic_version.version_num = '0014_merge_cards_rewards';

COMMIT;
