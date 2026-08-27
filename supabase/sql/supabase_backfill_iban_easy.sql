-- One-time backfill: rewrites every existing wallet IBAN from the old
-- "AURO" bank code to "EASY" (migration 0041_iban_easy_backfill), matching
-- backend/app/wallets/iban.py's post-rebrand generator. Keeps each wallet's
-- existing 16-digit account number and recomputes the 2-digit checksum
-- (ISO 7064 mod 97-10) for the new bank code — same formula as
-- supabase_add_wallet_iban.sql, with "EASY" pre-converted to digits
-- (E=14, A=10, S=28, Y=34) instead of "AURO" (A=10, U=30, R=27, O=24).
--
-- Idempotent: only touches rows whose bank-code segment is still "AURO";
-- safe to re-run.
--
-- Run this in the Supabase SQL Editor, after supabase_add_wallet_iban.sql
-- has already applied (every wallet must already have an iban).

BEGIN;

UPDATE wallets
SET iban = 'RO'
    || lpad((98 - ((14102834 || substring(iban from 9 for 16) || '272400')::numeric % 97))::text, 2, '0')
    || 'EASY'
    || substring(iban from 9 for 16)
WHERE substring(iban from 5 for 4) = 'AURO';

COMMIT;
