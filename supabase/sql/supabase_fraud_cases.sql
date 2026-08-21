-- Adds fraud_cases and fraud_flags (migration 0026_fraud_cases) — the
-- deterministic fraud engine's output tables. See
-- backend/migrations/versions/0026_fraud_cases.py for the source of truth.
--
-- Idempotent: safe to re-run regardless of whether it already applied.
--
-- Run this in the Supabase SQL Editor AFTER supabase_advance_to_0025_merge_heads.sql.

BEGIN;

DO $$ BEGIN
    CREATE TYPE fraud_case_status AS ENUM ('PENDING_REVIEW', 'APPROVED', 'REJECTED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE fraud_flag_code AS ENUM (
        'NEW_DEVICE', 'HIGH_AMOUNT', 'UNUSUAL_COUNTRY', 'REWARD_ABUSE_PATTERN', 'HIGH_VELOCITY'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS fraud_cases (
    id UUID PRIMARY KEY,
    transaction_id UUID NOT NULL UNIQUE REFERENCES transactions(id),
    user_id UUID NOT NULL REFERENCES users(id),
    risk_score NUMERIC(5, 2) NOT NULL,
    status fraud_case_status NOT NULL DEFAULT 'PENDING_REVIEW',
    hold_amount NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_by_admin_id UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    agent_analysis TEXT
);

CREATE TABLE IF NOT EXISTS fraud_flags (
    id UUID PRIMARY KEY,
    fraud_case_id UUID NOT NULL REFERENCES fraud_cases(id),
    code fraud_flag_code NOT NULL,
    points NUMERIC(5, 2) NOT NULL,
    description VARCHAR(255) NOT NULL
);

-- Only fires from the known pre-0026 state, so it can't regress a database
-- that's already past this point (same idempotency guard style as
-- supabase_advance_to_0025_merge_heads.sql).
UPDATE alembic_version
SET version_num = '0026_fraud_cases'
WHERE version_num = '0025_merge_heads';

COMMIT;
