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

INSERT INTO reward_tiers (id, name, min_lifetime_points, perks, sort_order) VALUES ('7674f6c5-2838-476c-a76e-e1cab2ca08c6', 'STANDARD', 0, 'Earn 1 point per RON spent|Redeem points in the benefits catalog', 0);

INSERT INTO reward_tiers (id, name, min_lifetime_points, perks, sort_order) VALUES ('327c5c24-1ef6-4748-9010-037c27298041', 'PREMIUM', 2000, 'Airport lounge access|Priority customer support|Early access to new cashback offers', 1);

INSERT INTO reward_tiers (id, name, min_lifetime_points, perks, sort_order) VALUES ('82ee5d9e-e1a7-4f4d-80ad-18c41854d98a', 'METAL', 8000, 'Unlimited airport lounge access|Dedicated concierge support|Premium travel insurance', 2);

UPDATE alembic_version SET version_num='0005_reward_tiers_benefits' WHERE alembic_version.version_num = '0004_merchants_rewards';


-- Running upgrade 0009_merge_payments_cards, 0005_reward_tiers_benefits -> 0010_merge_rewards
DELETE FROM alembic_version WHERE alembic_version.version_num = '0009_merge_payments_cards';
UPDATE alembic_version SET version_num='0010_merge_rewards' WHERE alembic_version.version_num = '0005_reward_tiers_benefits';
