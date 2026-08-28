-- Adds MT940 to the export_format enum (migration 0043_export_format_mt940)
-- so business transaction exports can be generated as an MT940 SWIFT
-- statement, alongside the existing CSV/XLSX/PDF formats.
--
-- Idempotent: ADD VALUE IF NOT EXISTS is safe to re-run.
--
-- Run this in the Supabase SQL Editor.

BEGIN;

ALTER TYPE export_format ADD VALUE IF NOT EXISTS 'MT940';

COMMIT;
