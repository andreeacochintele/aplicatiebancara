"""One spending-category vocabulary, shared by the Analytics donut, Budgets
and the new per-transaction picker.

Until now the two lists were unrelated. transaction_categories was seeded
with Groceries/Restaurants/Transport/Shopping/Bills/Income/Transfers/Other
and never assigned to anything, while the donut and Budgets both grouped by
Merchant.category, whose live values are Retail, Food, Fuel, Travel and
Entertainment. Letting a user re-file a payment from the first list would
have split one kind of spending across two slices that never add up.

Three things happen here:

  1. Merchants move from "Retail" to "Shopping". These name the same
     spending (Nike, Zara, eMAG) and only one can be in the picker; the
     merchants are the ones that have to move, because leaving them on
     "Retail" while the picker offers only "Shopping" would recreate exactly
     the split vocabulary this migration exists to remove.
  2. Restaurants is folded into Food, and Income/Transfers are dropped —
     neither is a purchase, so neither belongs in a spending view.
  3. The remaining everyday categories are added.

The deletes skip any category already assigned to a transaction, so this
cannot orphan a Transaction.category_id. Nothing assigns one today, but
that stops being true the moment the feature this migration exists for
ships, and a re-run has to stay safe.

Revision ID: 0052_unify_transaction_categories
Revises: 0051_one_folder_per_transaction
Create Date: 2026-08-29
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0052_unify_transaction_categories"
down_revision: Union[str, None] = "0051_one_folder_per_transaction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every value Merchant.category holds after the Retail -> Shopping move
# (Food, Fuel, Travel, Entertainment, Shopping — see app/seed.py), plus the
# everyday categories a user reaches for that no seeded merchant covers.
# "Other" doubles as the fallback an uncategorised payment is grouped under
# (transactions/categories.py).
_CATEGORIES = [
    "Food",
    "Groceries",
    "Entertainment",
    "Fuel",
    "Transport",
    "Shopping",
    "Travel",
    "Bills",
    "Health",
    "Subscriptions",
    "Sports & Fitness",
    "Education",
    "Beauty & Personal care",
    "Gifts & Charity",
    "Other",
]

# Restaurants is covered by Food; Income and Transfers are not purchases;
# Retail is now Shopping.
_REMOVED = ["Restaurants", "Income", "Transfers", "Retail"]


def upgrade() -> None:
    op.execute("UPDATE merchants SET category = 'Shopping' WHERE category = 'Retail'")

    categories = sa.table("transaction_categories", sa.column("id"), sa.column("name"))
    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(sa.select(categories.c.name))}

    missing = [name for name in _CATEGORIES if name not in existing]
    if missing:
        op.bulk_insert(categories, [{"id": str(uuid.uuid4()), "name": name} for name in missing])

    op.execute(
        sa.text(
            """
            DELETE FROM transaction_categories
            WHERE name = ANY(:removed)
              AND id NOT IN (
                  SELECT category_id FROM transactions WHERE category_id IS NOT NULL
              )
            """
        ).bindparams(sa.bindparam("removed", value=_REMOVED, type_=sa.ARRAY(sa.String)))
    )


def downgrade() -> None:
    # Restores the old names and moves merchants back. The categories added
    # here are left in place: a transaction may by then be pointing at one,
    # and deleting it would orphan that reference.
    op.execute("UPDATE merchants SET category = 'Retail' WHERE category = 'Shopping'")

    categories = sa.table("transaction_categories", sa.column("id"), sa.column("name"))
    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(sa.select(categories.c.name))}
    restored = [name for name in _REMOVED if name not in existing]
    if restored:
        op.bulk_insert(categories, [{"id": str(uuid.uuid4()), "name": name} for name in restored])
