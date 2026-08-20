-- Supabase manual update for the Notification Center.
-- Generated for migration:
--   0019_notifications
--
-- Run this in Supabase SQL Editor when DATABASE_BACKEND=supabase_rest is used.
-- Pure addition (new table only) — safe to run regardless of which of the
-- two current divergent heads (0016_benefit_card_tier_gating /
-- 0022_merge_heads) master's alembic_version bookkeeping is actually at,
-- so this intentionally does not touch that table. Reconcile it once
-- those heads are merged.

BEGIN;

DO $$ BEGIN
    CREATE TYPE notification_type AS ENUM (
        'TRANSACTION', 'FRAUD', 'PAYMENT_REMINDER', 'CASHBACK', 'CREDIT', 'SPLIT_BILL', 'SYSTEM'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    type notification_type NOT NULL,
    title VARCHAR(200) NOT NULL,
    message VARCHAR(1000) NOT NULL,
    related_transaction_id UUID REFERENCES transactions(id),
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications(user_id);

COMMIT;
