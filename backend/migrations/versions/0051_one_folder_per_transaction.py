"""Restrict a transaction to a single transaction folder.

The table only enforced UNIQUE(folder_id, transaction_id), so the same
payment could sit in several folders at once. Each folder counts it toward
its own total and can be split independently, so settling one folder leaves
the others still claiming money that has already been accounted for.

Deduplicates first, keeping the earliest membership by added_at (the folder
it was originally filed into) and dropping the later ones — the constraint
cannot be added while a violating row exists. Run the read-only query in
supabase/sql/supabase_one_folder_per_transaction.sql first if you want to
see what that will remove.

The existing UNIQUE(folder_id, transaction_id) is left in place: it is
implied by this one and dropping a constraint by name is the kind of thing
that diverges between the Alembic history and the hand-mirrored Supabase
schema.

Note this is a global uniqueness, not per-user. Equivalent today, because
only CARD_PAYMENT/SCHEDULED_PAYMENT/CASHBACK are folder-eligible and none of
those are visible to a second user the way a transfer's receiving side is
(TransactionRepository.get_for_user matches on the destination wallet too).
If a two-sided transaction type ever becomes folder-eligible, this needs to
become UNIQUE(owner_user_id, transaction_id) with owner_user_id denormalized
onto the item row.

Revision ID: 0051_one_folder_per_transaction
Revises: 0050_agent_transfer_assistant_name
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0051_one_folder_per_transaction"
down_revision: Union[str, None] = "0050_agent_transfer_assistant_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM transaction_folder_items
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY transaction_id
                           ORDER BY added_at ASC, id ASC
                       ) AS position
                FROM transaction_folder_items
            ) ranked
            WHERE position > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_transaction_folder_items_transaction",
        "transaction_folder_items",
        ["transaction_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_transaction_folder_items_transaction",
        "transaction_folder_items",
        type_="unique",
    )
