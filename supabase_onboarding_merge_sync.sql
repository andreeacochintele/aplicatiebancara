-- Supabase manual update to bring the shared REST-backend schema up to
-- alembic head 0023_merge_heads, after merging origin/master into
-- feature/user-onboarding-profile and generating the 0023_merge_heads
-- migration to reconcile the two resulting heads
-- (0022_merge_heads vs 0022_user_onboarding_profile).
--
-- Checked live against Supabase before writing this (alembic_version was
-- still at 0020_redemption_expiry). Three sections below, in dependency
-- order:
--
-- 1) 0019_credit_profile_currency + 0020_credit_loan_product_type
--    (Credit branch, PR #22 -- already on master before this branch's
--    merge-base, but never applied here: credit_profiles.currency and
--    credit_applications.loan_product_type genuinely don't exist yet).
--    Not onboarding work -- flagging for Luca/cards-credit visibility.
--
-- 2) 0022_user_onboarding_profile backfill only. The tables, enums and
--    initial backfill were already applied manually last night -- verified
--    live (17/20 users have rows). This only re-runs the backfill inserts
--    (ON CONFLICT DO NOTHING, safe) to cover the 3 users created since.
--    No CREATE TABLE / CREATE TYPE here on purpose.
--
-- 3) alembic_version bookkeeping, guarded like every other script in this
--    repo so it can't regress or double-apply regardless of run order.
--
-- Idempotent: safe to run regardless of what has already been applied.

BEGIN;

-- 1) 0019_credit_profile_currency
ALTER TABLE credit_profiles ADD COLUMN IF NOT EXISTS currency VARCHAR(3);

UPDATE credit_profiles SET currency = 'RON' WHERE currency IS NULL;

ALTER TABLE credit_profiles ALTER COLUMN currency SET NOT NULL;

-- 1) 0020_credit_loan_product_type
DO $$
BEGIN
    CREATE TYPE loan_product_type AS ENUM (
        'PERSONAL_LOAN',
        'MORTGAGE',
        'AUTO_LOAN',
        'STUDENT_LOAN',
        'HOME_IMPROVEMENT',
        'DEBT_CONSOLIDATION'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE credit_applications ADD COLUMN IF NOT EXISTS loan_product_type loan_product_type;

UPDATE credit_applications
SET loan_product_type = 'PERSONAL_LOAN'
WHERE type = 'PERSONAL_LOAN' AND loan_product_type IS NULL;

-- 2) 0022_user_onboarding_profile -- backfill only, for users created after
-- last night's manual table setup.
INSERT INTO user_onboarding_states (
    id, user_id, pending_step, completed, step_4_skipped,
    identity_document_status, created_at, updated_at
)
SELECT gen_random_uuid(), users.id, NULL, TRUE, FALSE, 'NOT_STARTED', now(), now()
FROM users
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO user_profiles (id, user_id, created_at, updated_at)
SELECT gen_random_uuid(), users.id, now(), now()
FROM users
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO user_addresses (id, user_id, created_at, updated_at)
SELECT gen_random_uuid(), users.id, now(), now()
FROM users
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO user_employment_profiles (id, user_id, created_at, updated_at)
SELECT gen_random_uuid(), users.id, now(), now()
FROM users
ON CONFLICT (user_id) DO NOTHING;

-- 3) Advance the version marker to the merged head. Only fires from the
-- known pre-merge states, so it can't regress a database that's already
-- past this point or that another branch's script has moved elsewhere.
UPDATE alembic_version
SET version_num = '0023_merge_heads'
WHERE version_num IN (
    '0020_redemption_expiry',
    '0022_merge_heads',
    '0022_user_onboarding_profile'
);

COMMIT;
