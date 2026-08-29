-- Creates business_profiles (migration 0044_business_profiles):
-- company_name/tax_id/registration_number/business_category/representative_name
-- for BUSINESS accounts, plus is_active. One-to-many with users (a user can
-- represent more than one company) — is_active marks the currently
-- selected one, same invariant as wallets.is_main.
--
-- Idempotent AND safe to re-run against a table that already exists in an
-- older partial form: an earlier draft of this script (CREATE TABLE only,
-- no representative_name/is_active) already ran against this database, so
-- CREATE TABLE IF NOT EXISTS alone would silently no-op and leave those two
-- columns missing. The ALTER TABLE ADD COLUMN IF NOT EXISTS lines below
-- backfill them onto that already-existing table.
--
-- Also drops a stray UNIQUE(user_id) constraint (business_profiles_user_id_key)
-- left over from an even earlier single-company version of this table. The
-- CREATE TABLE above never declares user_id UNIQUE (correctly — one user can
-- own several companies, is_active picks the current one), but a table
-- created before that was decided still has the old constraint live, which
-- makes POST /business/profiles for a second company fail with a 409
-- ("duplicate key value violates unique constraint") even though the exact
-- same request already works fine locally. Confirmed live against the
-- shared project on 2026-08-29.
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

ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS representative_name VARCHAR(200);
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE business_profiles DROP CONSTRAINT IF EXISTS business_profiles_user_id_key;

-- Backfill: any row inserted before is_active existed defaulted to FALSE
-- above. For a user with no active company at all, mark their oldest one
-- active — matches the app's own "first company is active by default"
-- rule (BusinessProfileService.create_profile).
UPDATE business_profiles bp
SET is_active = TRUE
WHERE bp.id = (
    SELECT id FROM business_profiles
    WHERE user_id = bp.user_id
    ORDER BY created_at ASC
    LIMIT 1
)
AND NOT EXISTS (
    SELECT 1 FROM business_profiles WHERE user_id = bp.user_id AND is_active = TRUE
);

CREATE INDEX IF NOT EXISTS ix_business_profiles_user_id ON business_profiles (user_id);

COMMIT;
