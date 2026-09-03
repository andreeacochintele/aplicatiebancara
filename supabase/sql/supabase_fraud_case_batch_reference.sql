-- Adds fraud_cases.batch_reference so the admin Fraud Review page can group
-- and decide together every case created from the same bulk-transfer submit,
-- instead of one unrelated-looking case per row. See
-- backend/migrations/versions/0054_fraud_case_batch_reference.py for the
-- source of truth.
--
-- Idempotent: safe to re-run (ADD COLUMN IF NOT EXISTS).
--
-- Run this in the Supabase SQL Editor once alembic_version has reached
-- 0053_merge_heads.

BEGIN;

ALTER TABLE fraud_cases ADD COLUMN IF NOT EXISTS batch_reference VARCHAR(64);

UPDATE alembic_version
SET version_num = '0054_fraud_case_batch_reference'
WHERE version_num = '0053_merge_heads';

COMMIT;
