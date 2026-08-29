-- Mirrors backend/migrations/versions/0049_fraud_repeated_transfer_pattern.py
-- for the Supabase (PostgREST) backend: adds REPEATED_TRANSFER_PATTERN to the
-- fraud_flag_code enum, the transfer-side counterpart of
-- REWARD_ABUSE_PATTERN. See backend/app/fraud/service.py for when it fires.
--
-- Additive only: no existing fraud_flags row changes and every previously
-- valid code stays valid.
--
-- Idempotent: safe to re-run.
-- Prerequisite: supabase_fraud_cases.sql must already be applied (it is what
-- creates the fraud_flag_code type).
--
-- ALTER TYPE ... ADD VALUE cannot run inside a transaction block on older
-- Postgres, so this file deliberately has no BEGIN/COMMIT wrapper.

ALTER TYPE fraud_flag_code ADD VALUE IF NOT EXISTS 'REPEATED_TRANSFER_PATTERN';
