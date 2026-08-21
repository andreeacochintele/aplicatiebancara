-- Advances alembic_version the last step to 0025_merge_heads, after this
-- branch renamed a too-long revision id (0024_merge_notifications_card_tier,
-- 35 chars, overflows alembic_version.version_num's VARCHAR(32)) to
-- 0024_merge_notif_card and added 0025_merge_heads to reconcile it with
-- master's own independent resolution of the same 0016/0023 head split.
--
-- No DDL: 0025_merge_heads (like 0023_merge_heads/0024_merge_heads before
-- it) is a no-op merge migration — only the version marker needs to move.
--
-- Idempotent: only fires from known pre-0025 states, so it can't regress a
-- database that's already past this point.

BEGIN;

UPDATE alembic_version
SET version_num = '0025_merge_heads'
WHERE version_num IN (
    '0022_merge_heads',
    '0022_user_onboarding_profile',
    '0023_merge_heads',
    '0023_notifications',
    '0024_merge_heads',
    '0024_merge_notif_card'
);

COMMIT;
