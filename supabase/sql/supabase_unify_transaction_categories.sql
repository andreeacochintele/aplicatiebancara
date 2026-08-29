-- Mirrors migration 0052_unify_transaction_categories: one spending-category
-- vocabulary shared by the Analytics donut, Budgets and the new
-- per-transaction picker.
--
-- Until now the two lists were unrelated — transaction_categories held
-- Groceries/Restaurants/Transport/Shopping/Bills/Income/Transfers/Other and
-- was never assigned to anything, while the donut grouped by
-- Merchant.category (Retail, Food, Fuel, Travel, Entertainment).
--
-- Three things happen:
--   1. Merchants move Retail -> Shopping (same spending; only one name can
--      be in the picker, and leaving merchants on the other one would
--      recreate the split vocabulary this fixes).
--   2. Restaurants folds into Food; Income and Transfers are dropped as not
--      being purchases.
--   3. The remaining everyday categories are added.
--
-- Idempotent: inserts only what's missing, and drops obsolete names only
-- while no transaction points at them. Safe to re-run.


-- ---------------------------------------------------------------------
-- STEP 1 — READ-ONLY. What this will change, before it changes it.
-- ---------------------------------------------------------------------
--
-- SELECT category, count(*) AS merchants
-- FROM merchants GROUP BY category ORDER BY category;
--
-- SELECT name FROM transaction_categories ORDER BY name;


-- ---------------------------------------------------------------------
-- STEP 2 — apply.
-- ---------------------------------------------------------------------

BEGIN;

UPDATE merchants SET category = 'Shopping' WHERE category = 'Retail';

INSERT INTO transaction_categories (id, name)
SELECT gen_random_uuid(), name
FROM (VALUES
    ('Food'), ('Groceries'), ('Entertainment'), ('Fuel'), ('Transport'),
    ('Shopping'), ('Travel'), ('Bills'), ('Health'), ('Subscriptions'),
    ('Sports & Fitness'), ('Education'), ('Beauty & Personal care'),
    ('Gifts & Charity'), ('Other')
) AS wanted(name)
WHERE NOT EXISTS (
    SELECT 1 FROM transaction_categories existing WHERE existing.name = wanted.name
);

DELETE FROM transaction_categories
WHERE name IN ('Restaurants', 'Income', 'Transfers', 'Retail')
  AND id NOT IN (SELECT category_id FROM transactions WHERE category_id IS NOT NULL);

COMMIT;


-- Verificare dupa (read-only) — trebuie sa dea 15 randuri si niciun
-- merchant ramas pe 'Retail':
--
-- SELECT name FROM transaction_categories ORDER BY name;
-- SELECT count(*) AS retail_ramasi FROM merchants WHERE category = 'Retail';
