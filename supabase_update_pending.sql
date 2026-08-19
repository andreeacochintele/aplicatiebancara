BEGIN;

-- Running upgrade 0010_merge_rewards -> 0011_card_tiers

CREATE TYPE card_tier AS ENUM ('REGULAR', 'GOLD', 'PLATINUM');

ALTER TABLE cards ADD COLUMN tier card_tier;

UPDATE cards SET tier = 'REGULAR' WHERE type IN ('DEBIT', 'CREDIT') AND tier IS NULL;

UPDATE alembic_version SET version_num='0011_card_tiers' WHERE alembic_version.version_num = '0010_merge_rewards';

-- Running upgrade 0011_card_tiers -> 0012_card_mock_cvv

ALTER TABLE cards ADD COLUMN mock_cvv VARCHAR(3);

UPDATE cards SET mock_cvv = lpad((floor(random() * 1000))::int::text, 3, '0') WHERE mock_cvv IS NULL;

ALTER TABLE cards ALTER COLUMN mock_cvv SET NOT NULL;

UPDATE alembic_version SET version_num='0012_card_mock_cvv' WHERE alembic_version.version_num = '0011_card_tiers';

-- Running upgrade 0012_card_mock_cvv -> 0013_card_mock_pan

ALTER TABLE cards ADD COLUMN mock_pan VARCHAR(19);

UPDATE cards
        SET mock_pan =
            '4000 '
            || lpad((floor(random() * 10000))::int::text, 4, '0')
            || ' '
            || lpad((floor(random() * 10000))::int::text, 4, '0')
            || ' '
            || last_four
        WHERE mock_pan IS NULL;

ALTER TABLE cards ALTER COLUMN mock_pan SET NOT NULL;

UPDATE alembic_version SET version_num='0013_card_mock_pan' WHERE alembic_version.version_num = '0012_card_mock_cvv';

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

