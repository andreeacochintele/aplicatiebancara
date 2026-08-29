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

A retired category's transactions are re-filed onto its successor before it
is deleted, so nothing is orphaned and nothing survives the merge. Guarding
the delete on "not referenced" instead would quietly leave a category the
user had already picked sitting in the picker next to the one it was meant
to fold into.

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

# Retired names, and where a transaction already filed under one should end
# up. Restaurants and Retail have a real successor; Income and Transfers do
# not — nothing in a spending vocabulary means "this was not spending", so
# those transactions go back to inheriting their merchant's category (None
# clears Transaction.category_id).
_MERGED_INTO: dict[str, str | None] = {
    "Restaurants": "Food",
    "Retail": "Shopping",
    "Income": None,
    "Transfers": None,
}


def upgrade() -> None:
    op.execute("UPDATE merchants SET category = 'Shopping' WHERE category = 'Retail'")

    categories = sa.table("transaction_categories", sa.column("id"), sa.column("name"))
    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(sa.select(categories.c.name))}

    missing = [name for name in _CATEGORIES if name not in existing]
    if missing:
        op.bulk_insert(categories, [{"id": str(uuid.uuid4()), "name": name} for name in missing])

    # Re-file before deleting, or a category a user had already picked would
    # survive the merge (a delete guarded on "not referenced" simply skips
    # it) and keep showing up in the picker as a duplicate of the name it
    # was supposed to fold into.
    for retired, successor in _MERGED_INTO.items():
        op.execute(
            sa.text(
                """
                UPDATE transactions
                SET category_id = (
                    SELECT id FROM transaction_categories WHERE name = :successor
                )
                WHERE category_id = (
                    SELECT id FROM transaction_categories WHERE name = :retired
                )
                """
            ).bindparams(sa.bindparam("successor", value=successor), sa.bindparam("retired", value=retired))
        )

    op.execute(
        sa.text("DELETE FROM transaction_categories WHERE name = ANY(:removed)").bindparams(
            sa.bindparam("removed", value=list(_MERGED_INTO), type_=sa.ARRAY(sa.String))
        )
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
