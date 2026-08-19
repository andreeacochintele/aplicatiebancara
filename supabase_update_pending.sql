BEGIN;

-- Running upgrade 0010_merge_rewards -> 0011_reward_tx_unique

ALTER TABLE reward_transactions ADD CONSTRAINT uq_reward_transactions_source_transaction_id UNIQUE (source_transaction_id);

INSERT INTO alembic_version (version_num) VALUES ('0011_reward_tx_unique') RETURNING alembic_version.version_num;

-- Running upgrade 0011_reward_tx_unique -> 0012_merchant_verified

ALTER TABLE merchants ADD COLUMN verified BOOLEAN DEFAULT false NOT NULL;

UPDATE alembic_version SET version_num='0012_merchant_verified' WHERE alembic_version.version_num = '0011_reward_tx_unique';

-- Running upgrade 0012_merchant_verified, 0013_card_mock_pan -> 0014_merge_cards_rewards

DELETE FROM alembic_version WHERE alembic_version.version_num = '0012_merchant_verified';

UPDATE alembic_version SET version_num='0014_merge_cards_rewards' WHERE alembic_version.version_num = '0013_card_mock_pan';

COMMIT;
