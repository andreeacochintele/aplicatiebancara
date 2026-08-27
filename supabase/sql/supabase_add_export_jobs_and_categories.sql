-- Adds transaction_categories and exports (migration
-- 0036_export_jobs_and_categories) — lets business transaction exports
-- resolve a real category name instead of a bare UUID, and logs every
-- generated export so it shows up in export history / can be re-downloaded.
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

CREATE TABLE IF NOT EXISTS transaction_categories (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO transaction_categories (id, name)
VALUES
    (gen_random_uuid(), 'Groceries'),
    (gen_random_uuid(), 'Restaurants'),
    (gen_random_uuid(), 'Transport'),
    (gen_random_uuid(), 'Shopping'),
    (gen_random_uuid(), 'Bills'),
    (gen_random_uuid(), 'Income'),
    (gen_random_uuid(), 'Transfers'),
    (gen_random_uuid(), 'Other')
ON CONFLICT (name) DO NOTHING;

DO $$ BEGIN
    CREATE TYPE export_type AS ENUM ('STATEMENT', 'BUSINESS_TRANSACTIONS');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE export_format AS ENUM ('CSV', 'XLSX', 'PDF');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE export_status AS ENUM ('PROCESSING', 'READY', 'FAILED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS exports (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    type export_type NOT NULL,
    format export_format NOT NULL,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    filters JSONB,
    status export_status NOT NULL DEFAULT 'READY',
    file_path VARCHAR(500),
    content TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_exports_user_id ON exports (user_id);

COMMIT;
