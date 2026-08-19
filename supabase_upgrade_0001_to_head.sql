BEGIN;

-- Running upgrade 0001 -> 0002

CREATE TYPE fx_quote_status AS ENUM ('CREATED', 'ACCEPTED', 'EXPIRED');

CREATE TABLE fx_quotes (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    source_currency VARCHAR(3) NOT NULL, 
    target_currency VARCHAR(3) NOT NULL, 
    source_amount NUMERIC(18, 2) NOT NULL, 
    target_amount NUMERIC(18, 2) NOT NULL, 
    exchange_rate NUMERIC(18, 8) NOT NULL, 
    fee NUMERIC(18, 2) NOT NULL, 
    status fx_quote_status DEFAULT 'CREATED' NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

ALTER TABLE transactions ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE user_devices ALTER COLUMN first_seen_at SET NOT NULL;

ALTER TABLE user_devices ALTER COLUMN last_seen_at SET NOT NULL;

ALTER TABLE user_sessions ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE user_sessions ALTER COLUMN last_activity_at SET NOT NULL;

ALTER TABLE users ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE users ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE wallet_ledger_entries ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE wallets ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE wallets ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE users DROP CONSTRAINT users_email_key;

ALTER TABLE users DROP CONSTRAINT users_phone_key;

DROP INDEX ix_users_email;

CREATE UNIQUE INDEX ix_users_email ON users (email);

DROP INDEX ix_users_phone;

CREATE UNIQUE INDEX ix_users_phone ON users (phone);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TYPE budget_period AS ENUM ('WEEKLY', 'MONTHLY');

CREATE TABLE budgets (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    category_id UUID, 
    name VARCHAR(100) NOT NULL, 
    limit_amount NUMERIC(18, 2) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    period budget_period DEFAULT 'MONTHLY' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE savings_goals (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    target_amount NUMERIC(18, 2) NOT NULL, 
    current_amount NUMERIC(18, 2) DEFAULT '0' NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    target_date DATE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004_cards_core

CREATE TYPE card_type AS ENUM ('DEBIT', 'CREDIT', 'ONE_TIME');

CREATE TYPE card_status AS ENUM ('ACTIVE', 'FROZEN', 'EXPIRED', 'CANCELLED');

CREATE TABLE cards (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    default_wallet_id UUID, 
    type card_type NOT NULL, 
    status card_status NOT NULL, 
    masked_pan VARCHAR(19) NOT NULL, 
    last_four VARCHAR(4) NOT NULL, 
    expiration_month INTEGER NOT NULL, 
    expiration_year INTEGER NOT NULL, 
    one_time_remaining INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    FOREIGN KEY(default_wallet_id) REFERENCES wallets (id)
);

UPDATE alembic_version SET version_num='0004_cards_core' WHERE alembic_version.version_num = '0003';

-- Running upgrade 0004_cards_core -> 0005_card_payment_preferences

CREATE TABLE card_payment_preferences (
    card_id UUID NOT NULL, 
    preferred_wallet_id UUID, 
    allow_main_wallet_fx BOOLEAN DEFAULT false NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (card_id), 
    FOREIGN KEY(card_id) REFERENCES cards (id), 
    FOREIGN KEY(preferred_wallet_id) REFERENCES wallets (id)
);

UPDATE alembic_version SET version_num='0005_card_payment_preferences' WHERE alembic_version.version_num = '0004_cards_core';

-- Running upgrade 0005_card_payment_preferences -> 0006_credit_score_core

CREATE TABLE credit_profiles (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    current_score INTEGER DEFAULT '600' NOT NULL, 
    income NUMERIC(18, 2) DEFAULT '0' NOT NULL, 
    existing_debt NUMERIC(18, 2) DEFAULT '0' NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    UNIQUE (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE credit_score_history (
    id UUID NOT NULL, 
    credit_profile_id UUID NOT NULL, 
    score INTEGER NOT NULL, 
    reason_data JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(credit_profile_id) REFERENCES credit_profiles (id)
);

UPDATE alembic_version SET version_num='0006_credit_score_core' WHERE alembic_version.version_num = '0005_card_payment_preferences';

-- Running upgrade 0006_credit_score_core -> 0007_credit_applications

CREATE TYPE credit_application_type AS ENUM ('PERSONAL_LOAN', 'CREDIT_CARD');

CREATE TYPE credit_application_status AS ENUM ('DRAFT', 'PENDING', 'APPROVED', 'REJECTED');

CREATE TABLE credit_applications (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    type credit_application_type NOT NULL, 
    requested_amount NUMERIC(18, 2) NOT NULL, 
    requested_term_months INTEGER, 
    offered_interest_rate NUMERIC(5, 2), 
    offered_amount NUMERIC(18, 2), 
    credit_score_at_application INTEGER NOT NULL, 
    status credit_application_status DEFAULT 'PENDING' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    resolved_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

UPDATE alembic_version SET version_num='0007_credit_applications' WHERE alembic_version.version_num = '0006_credit_score_core';

-- Running upgrade 0007_credit_applications -> 0008_loans

CREATE TYPE loan_status AS ENUM ('ACTIVE', 'CLOSED', 'DEFAULTED');

CREATE TABLE loans (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    application_id UUID NOT NULL, 
    principal_amount NUMERIC(18, 2) NOT NULL, 
    interest_rate NUMERIC(5, 2) NOT NULL, 
    term_months INTEGER NOT NULL, 
    monthly_payment NUMERIC(18, 2) NOT NULL, 
    outstanding_principal NUMERIC(18, 2) NOT NULL, 
    status loan_status DEFAULT 'ACTIVE' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    closed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (application_id), 
    FOREIGN KEY(application_id) REFERENCES credit_applications (id)
);

UPDATE alembic_version SET version_num='0008_loans' WHERE alembic_version.version_num = '0007_credit_applications';

-- Running upgrade 0003 -> 0004_merchants_rewards

CREATE TYPE merchant_status AS ENUM ('ACTIVE', 'INACTIVE');

CREATE TABLE merchants (
    id UUID NOT NULL, 
    name VARCHAR(150) NOT NULL, 
    logo_url VARCHAR(500), 
    category VARCHAR(50) NOT NULL, 
    status merchant_status DEFAULT 'ACTIVE' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TYPE cashback_offer_status AS ENUM ('ACTIVE', 'EXPIRED');

CREATE TABLE cashback_offers (
    id UUID NOT NULL, 
    merchant_id UUID NOT NULL, 
    cashback_percent NUMERIC(5, 2) NOT NULL, 
    maximum_cashback NUMERIC(18, 2), 
    minimum_spend NUMERIC(18, 2), 
    start_date DATE NOT NULL, 
    end_date DATE NOT NULL, 
    status cashback_offer_status DEFAULT 'ACTIVE' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(merchant_id) REFERENCES merchants (id)
);

CREATE TABLE reward_accounts (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    points_balance INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TYPE reward_transaction_type AS ENUM ('EARN', 'SPEND', 'ADJUSTMENT');

CREATE TABLE reward_transactions (
    id UUID NOT NULL, 
    reward_account_id UUID NOT NULL, 
    source_transaction_id UUID, 
    type reward_transaction_type NOT NULL, 
    points INTEGER NOT NULL, 
    description VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(reward_account_id) REFERENCES reward_accounts (id), 
    FOREIGN KEY(source_transaction_id) REFERENCES transactions (id)
);

INSERT INTO alembic_version (version_num) VALUES ('0004_merchants_rewards') RETURNING alembic_version.version_num;

-- Running upgrade 0004_merchants_rewards -> 0005_reward_tiers_benefits

ALTER TABLE reward_accounts ADD COLUMN lifetime_points_earned INTEGER DEFAULT '0' NOT NULL;

CREATE TABLE reward_tiers (
    id UUID NOT NULL, 
    name VARCHAR(50) NOT NULL, 
    min_lifetime_points INTEGER NOT NULL, 
    perks VARCHAR(1000) NOT NULL, 
    sort_order INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TYPE benefit_category AS ENUM ('LOUNGE_ACCESS', 'RETAIL_DISCOUNT', 'TRAVEL', 'INSURANCE', 'OTHER');

CREATE TYPE benefit_status AS ENUM ('ACTIVE', 'INACTIVE');

CREATE TABLE reward_benefits (
    id UUID NOT NULL, 
    name VARCHAR(150) NOT NULL, 
    category benefit_category NOT NULL, 
    description VARCHAR(500) NOT NULL, 
    points_cost INTEGER, 
    min_tier_id UUID, 
    partner_name VARCHAR(150), 
    status benefit_status DEFAULT 'ACTIVE' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(min_tier_id) REFERENCES reward_tiers (id)
);

CREATE TABLE benefit_redemptions (
    id UUID NOT NULL, 
    reward_account_id UUID NOT NULL, 
    benefit_id UUID NOT NULL, 
    reward_transaction_id UUID, 
    points_spent INTEGER DEFAULT '0' NOT NULL, 
    redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(reward_account_id) REFERENCES reward_accounts (id), 
    FOREIGN KEY(benefit_id) REFERENCES reward_benefits (id), 
    FOREIGN KEY(reward_transaction_id) REFERENCES reward_transactions (id)
);

INSERT INTO reward_tiers (id, name, min_lifetime_points, perks, sort_order) VALUES ('5448818a-16c8-47d7-9449-842224fefd28', 'STANDARD', 0, 'Earn 1 point per RON spent|Redeem points in the benefits catalog', 0);

INSERT INTO reward_tiers (id, name, min_lifetime_points, perks, sort_order) VALUES ('cf7e728a-92a3-4fb9-84f2-e49a8d2a08bf', 'PREMIUM', 2000, 'Airport lounge access|Priority customer support|Early access to new cashback offers', 1);

INSERT INTO reward_tiers (id, name, min_lifetime_points, perks, sort_order) VALUES ('2d69e296-dafc-4f1a-b4fa-5fa2c9b60d44', 'METAL', 8000, 'Unlimited airport lounge access|Dedicated concierge support|Premium travel insurance', 2);

UPDATE alembic_version SET version_num='0005_reward_tiers_benefits' WHERE alembic_version.version_num = '0004_merchants_rewards';

-- Running upgrade 0003 -> 0004

CREATE TABLE beneficiaries (
    id UUID NOT NULL, 
    owner_user_id UUID NOT NULL, 
    beneficiary_user_id UUID, 
    name VARCHAR(255) NOT NULL, 
    iban VARCHAR(34), 
    phone VARCHAR(32), 
    is_favorite BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_user_id) REFERENCES users (id), 
    FOREIGN KEY(beneficiary_user_id) REFERENCES users (id)
);

CREATE INDEX ix_beneficiaries_owner_user_id ON beneficiaries (owner_user_id);

INSERT INTO alembic_version (version_num) VALUES ('0004') RETURNING alembic_version.version_num;

-- Running upgrade 0004 -> 0005

CREATE TYPE payment_request_status AS ENUM ('ACTIVE', 'PAID', 'CANCELLED', 'EXPIRED');

CREATE TABLE payment_requests (
    id UUID NOT NULL, 
    creator_user_id UUID NOT NULL, 
    destination_wallet_id UUID NOT NULL, 
    amount NUMERIC(18, 2), 
    currency VARCHAR(3) NOT NULL, 
    status payment_request_status DEFAULT 'ACTIVE' NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(creator_user_id) REFERENCES users (id), 
    FOREIGN KEY(destination_wallet_id) REFERENCES wallets (id)
);

CREATE INDEX ix_payment_requests_creator_user_id ON payment_requests (creator_user_id);

CREATE INDEX ix_payment_requests_destination_wallet_id ON payment_requests (destination_wallet_id);

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

-- Running upgrade 0005 -> 0006

CREATE TYPE scheduled_payment_frequency AS ENUM ('ONCE', 'WEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY');

CREATE TYPE scheduled_payment_status AS ENUM ('ACTIVE', 'PAUSED', 'CANCELLED');

CREATE TABLE scheduled_payments (
    id UUID NOT NULL, 
    owner_user_id UUID NOT NULL, 
    source_wallet_id UUID NOT NULL, 
    beneficiary_name VARCHAR(255) NOT NULL, 
    iban VARCHAR(34) NOT NULL, 
    amount NUMERIC(18, 2) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    frequency scheduled_payment_frequency NOT NULL, 
    next_run_on DATE NOT NULL, 
    notify_days_before INTEGER DEFAULT '0' NOT NULL, 
    status scheduled_payment_status DEFAULT 'ACTIVE' NOT NULL, 
    description VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_user_id) REFERENCES users (id), 
    FOREIGN KEY(source_wallet_id) REFERENCES wallets (id)
);

CREATE INDEX ix_scheduled_payments_owner_user_id ON scheduled_payments (owner_user_id);

CREATE INDEX ix_scheduled_payments_source_wallet_id ON scheduled_payments (source_wallet_id);

CREATE INDEX ix_scheduled_payments_status_next_run ON scheduled_payments (status, next_run_on);

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

-- Running upgrade 0006, 0008_loans -> 0009_merge_payments_cards

DELETE FROM alembic_version WHERE alembic_version.version_num = '0008_loans';

UPDATE alembic_version SET version_num='0009_merge_payments_cards' WHERE alembic_version.version_num = '0006';

-- Running upgrade 0009_merge_payments_cards, 0005_reward_tiers_benefits -> 0010_merge_rewards

DELETE FROM alembic_version WHERE alembic_version.version_num = '0009_merge_payments_cards';

UPDATE alembic_version SET version_num='0010_merge_rewards' WHERE alembic_version.version_num = '0005_reward_tiers_benefits';

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

