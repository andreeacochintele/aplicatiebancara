-- Adds the notifications table (migration 0023_notifications) — first real
-- use of the previously-empty app/notifications skeleton. Currently only
-- app/merchants/service.py writes to it (a "Cashback earned" notification
-- after crediting cashback), but the table is generic (type is plain text,
-- not an enum) so other modules can add their own notification types later
-- without a schema change here.
--
-- Idempotent: safe to re-run regardless of whether it already applied.
--
-- Run this in the Supabase SQL Editor AFTER supabase_update_pending.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    type VARCHAR(50) NOT NULL,
    title VARCHAR(150) NOT NULL,
    message VARCHAR(500) NOT NULL,
    related_transaction_id UUID,
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id);

-- 0023 is brand new (nothing else has been built on top of it yet), so
-- this can't regress a marker that's already ahead — unlike the blind
-- overwrite mistake in an earlier version of supabase_update_pending.sql,
-- there's no "ahead" state for this one to clobber.
UPDATE alembic_version
SET version_num = '0023_notifications'
WHERE version_num <> '0023_notifications';

COMMIT;
