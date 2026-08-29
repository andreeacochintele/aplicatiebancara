-- Mirrors migration 0051_one_folder_per_transaction: a transaction may sit
-- in at most one folder. Previously only UNIQUE(folder_id, transaction_id)
-- was enforced, so the same payment could be in several folders at once,
-- each counting it toward its own total and each splittable on its own.
--
-- Idempotent: safe to re-run.


-- ---------------------------------------------------------------------
-- STEP 1 — READ-ONLY. Run this first: it lists the memberships the
-- deduplication below would DELETE (every one after the earliest, per
-- transaction). If it returns no rows, nothing gets removed.
-- ---------------------------------------------------------------------
--
-- SELECT i.id, i.transaction_id, i.folder_id, f.name AS folder_name, i.added_at
-- FROM (
--     SELECT id, transaction_id, folder_id, added_at,
--            row_number() OVER (PARTITION BY transaction_id
--                               ORDER BY added_at ASC, id ASC) AS position
--     FROM transaction_folder_items
-- ) i
-- JOIN transaction_folders f ON f.id = i.folder_id
-- WHERE i.position > 1
-- ORDER BY i.transaction_id, i.added_at;


-- ---------------------------------------------------------------------
-- STEP 2 — deduplicate, then constrain. Keeps the earliest membership
-- (the folder the transaction was originally filed into).
-- ---------------------------------------------------------------------

BEGIN;

DELETE FROM transaction_folder_items
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               row_number() OVER (PARTITION BY transaction_id
                                  ORDER BY added_at ASC, id ASC) AS position
        FROM transaction_folder_items
    ) ranked
    WHERE position > 1
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_transaction_folder_items_transaction'
    ) THEN
        ALTER TABLE transaction_folder_items
            ADD CONSTRAINT uq_transaction_folder_items_transaction UNIQUE (transaction_id);
    END IF;
END $$;

COMMIT;
