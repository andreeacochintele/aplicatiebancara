-- One-time backfill: rewrites the description of transfers the Actions
-- Agent executed before the assistant rename, from "(asistent AI)" to
-- "(asistent Nova)" (migration 0050_agent_transfer_assistant_name),
-- matching what backend/app/ai/actions/service.py now writes.
--
-- The description is persisted text, not a label rendered at display time,
-- so rows written before the rename keep the old wording until rewritten.
--
-- Scoped to the exact parenthesised suffix, so a user-written description
-- that merely contains the words "asistent AI" is left untouched.
--
-- Idempotent: only matches rows still carrying the old suffix; safe to
-- re-run. Does NOT touch alembic_version.

BEGIN;

UPDATE transactions
SET description = replace(description, '(asistent AI)', '(asistent Nova)')
WHERE description LIKE '%(asistent AI)%';

COMMIT;


-- Verificare înainte (read-only) — câte rânduri sunt de schimbat:
--
-- SELECT count(*) FROM transactions WHERE description LIKE '%(asistent AI)%';
--
-- Verificare după — trebuie să dea 0 la prima și >0 la a doua:
--
-- SELECT
--     count(*) FILTER (WHERE description LIKE '%(asistent AI)%')   AS ramase_vechi,
--     count(*) FILTER (WHERE description LIKE '%(asistent Nova)%') AS redenumite
-- FROM transactions;
