"""Cascade card payment preferences on card delete.

Revision ID: 0016_card_preferences_cascade
Revises: 0015_credit_lifecycle
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_card_preferences_cascade"
down_revision: Union[str, None] = "0015_credit_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    constraint_name = bind.execute(
        sa.text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'card_payment_preferences'::regclass
              AND confrelid = 'cards'::regclass
              AND contype = 'f'
            LIMIT 1
            """
        )
    ).scalar()
    if constraint_name is not None:
        op.drop_constraint(constraint_name, "card_payment_preferences", type_="foreignkey")
    op.create_foreign_key(
        "card_payment_preferences_card_id_fkey",
        "card_payment_preferences",
        "cards",
        ["card_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("card_payment_preferences_card_id_fkey", "card_payment_preferences", type_="foreignkey")
    op.create_foreign_key(
        "card_payment_preferences_card_id_fkey",
        "card_payment_preferences",
        "cards",
        ["card_id"],
        ["id"],
    )
