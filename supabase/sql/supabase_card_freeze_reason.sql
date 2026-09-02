-- cards.freeze_reason / frozen_at / frozen_by_admin_id — fraud-hold card
-- freeze workflow. Additive, nullable. See
-- backend/migrations/versions/0049_card_freeze_reason.py.
--
-- Idempotent — safe to run regardless of prior state.
--
-- Deliberately does NOT touch alembic_version: as of this writing, Supabase's
-- alembic_version table has 4 unresolved heads (0024_merge_heads,
-- 0013_card_mock_pan, 0026_credit_card_accounts, 0035_credit_card_collateral)
-- — a pre-existing merge/tracking problem unrelated to this change. Bumping
-- version tracking here would just add a fifth guess on top of an already
-- broken picture. Resolve the multi-head situation first (see
-- docs/supabase_rest_backend.md), then decide how to reconcile the version
-- marker separately.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'card_freeze_reason') THEN
        CREATE TYPE card_freeze_reason AS ENUM ('USER_REQUESTED', 'FRAUD_HOLD');
    END IF;
END $$;

ALTER TABLE cards ADD COLUMN IF NOT EXISTS freeze_reason card_freeze_reason;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS frozen_at timestamptz;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS frozen_by_admin_id uuid REFERENCES users(id);

COMMIT;
