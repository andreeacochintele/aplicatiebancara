-- Adds transactions.batch_reference so the Bulk Transfer page can list past
-- batches — most rows never create a fraud_cases row (which already has its
-- own batch_reference, migration 0054) to carry that value on. See
-- backend/migrations/versions/0055_transaction_batch_reference.py for the
-- source of truth.
--
-- Idempotent: safe to re-run (ADD COLUMN IF NOT EXISTS).
--
-- Run this in the Supabase SQL Editor once alembic_version has reached
-- 0054_fraud_case_batch_reference.

BEGIN;

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS batch_reference VARCHAR(64);

UPDATE alembic_version
SET version_num = '0055_transaction_batch_reference'
WHERE version_num = '0054_fraud_case_batch_reference';

COMMIT;
