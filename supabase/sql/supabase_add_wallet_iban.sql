-- Adds a sandbox IBAN to every wallet (migration 0037_wallet_iban) —
-- generates one for each existing wallet and requires one going forward.
--
-- IBAN layout: RO + 2 check digits (ISO 7064 mod 97-10) + "EASY" bank code +
-- 16-digit account number, matching backend/app/wallets/iban.py exactly.
-- The check-digit formula below is that algorithm with "EASY" and "RO"
-- pre-converted to digits (E=14, A=10, S=28, Y=34), since both are fixed —
-- no need to loop character by character in SQL.
--
-- Idempotent: safe to re-run regardless of whether it already applied.
--
-- NOT applied automatically: Supabase's alembic_version currently has three
-- unresolved head rows (0024_merge_heads, 0013_card_mock_pan,
-- 0026_credit_card_accounts) — `python -m app.supabase_schema_diff` refuses
-- to generate a diff against a mid-merge state, and this script doesn't
-- touch alembic_version at all. Whoever applies this should reconcile those
-- heads separately (same pattern as the other supabase_advance_to_*.sql
-- files) before or after running this one.
--
-- Run this in the Supabase SQL Editor.

BEGIN;

ALTER TABLE wallets ADD COLUMN IF NOT EXISTS iban VARCHAR(34);

DO $$
DECLARE
    wallet_row RECORD;
    account_number TEXT;
    numeric_str TEXT;
    check_digits TEXT;
    candidate_iban TEXT;
BEGIN
    FOR wallet_row IN SELECT id FROM wallets WHERE iban IS NULL LOOP
        LOOP
            account_number := lpad(floor(random() * 1e16)::bigint::text, 16, '0');
            numeric_str := '14102834' || account_number || '272400';
            check_digits := lpad((98 - (numeric_str::numeric % 97))::text, 2, '0');
            candidate_iban := 'RO' || check_digits || 'EASY' || account_number;
            EXIT WHEN NOT EXISTS (SELECT 1 FROM wallets WHERE iban = candidate_iban);
        END LOOP;
        UPDATE wallets SET iban = candidate_iban WHERE id = wallet_row.id;
    END LOOP;
END $$;

ALTER TABLE wallets ALTER COLUMN iban SET NOT NULL;

DO $$ BEGIN
    ALTER TABLE wallets ADD CONSTRAINT uq_wallets_iban UNIQUE (iban);
EXCEPTION
    WHEN duplicate_object OR duplicate_table THEN NULL;
END $$;

COMMIT;
