-- Adds payment_requests.reference/note so a payment request can be sent as
-- an invoice (reference number + note), purely descriptive. See
-- backend/migrations/versions/0055_payment_request_reference.py for the
-- source of truth.
--
-- Idempotent: safe to re-run (ADD COLUMN IF NOT EXISTS).
--
-- Run this in the Supabase SQL Editor once alembic_version has reached
-- 0054_fraud_case_batch_reference. NOTE: another branch's
-- supabase_transaction_batch_reference.sql also advances from 0054 to its
-- own 0055 — apply only one of the two "advance past 0054" scripts here,
-- then apply the other's underlying ALTER TABLE by hand (or wait for the
-- merge migration) so alembic_version doesn't get double-advanced.

BEGIN;

ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS reference VARCHAR(50);
ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS note VARCHAR(500);

UPDATE alembic_version
SET version_num = '0055_payment_request_reference'
WHERE version_num = '0054_fraud_case_batch_reference';

COMMIT;
