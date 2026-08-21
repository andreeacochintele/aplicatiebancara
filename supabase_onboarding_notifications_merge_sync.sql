-- Advance alembic_version to 0024_merge_heads after reconciling this
-- branch's own 0023_merge_heads with master's 0023_notifications (both
-- independently descend from 0022_merge_heads). No DDL needed here: the
-- notifications table already exists (supabase_add_notifications_table.sql
-- was already run and unconditionally set alembic_version to
-- '0023_notifications', overwriting this branch's earlier
-- '0023_merge_heads' marker -- harmless, since both sides are additive
-- and already applied).
--
-- Idempotent: safe to run regardless of which of the two prior markers is
-- currently set.

BEGIN;

UPDATE alembic_version
SET version_num = '0024_merge_heads'
WHERE version_num IN ('0023_merge_heads', '0023_notifications');

COMMIT;
