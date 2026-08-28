-- Creates business_profiles (migration 0044_business_profiles):
-- company_name/tax_id/registration_number/business_category/representative_name
-- for BUSINESS accounts, plus is_active. One-to-many with users (a user can
-- represent more than one company) — is_active marks the currently
-- selected one, same invariant as wallets.is_main.
--
-- Idempotent: safe to re-run.
--
-- Run this in the Supabase SQL Editor.

BEGIN;

CREATE TABLE IF NOT EXISTS business_profiles (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    company_name VARCHAR(200) NOT NULL,
    representative_name VARCHAR(200),
    tax_id VARCHAR(50),
    registration_number VARCHAR(50),
    business_category VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_business_profiles_user_id ON business_profiles (user_id);

COMMIT;
