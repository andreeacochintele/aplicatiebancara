"""Add collateral tracking for secured credit cards.

Revision ID: 0035_credit_card_collateral
Revises: 0034_widen_alembic_version
Create Date: 2026-08-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_credit_card_collateral"
down_revision: Union[str, None] = "0034_widen_alembic_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credit_card_accounts",
        sa.Column("collateral_wallet_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "credit_card_accounts",
        sa.Column("collateral_amount", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
    )
    op.create_foreign_key(
        "fk_credit_card_accounts_collateral_wallet_id_wallets",
        "credit_card_accounts",
        "wallets",
        ["collateral_wallet_id"],
        ["id"],
    )
    op.alter_column("credit_card_accounts", "collateral_amount", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "fk_credit_card_accounts_collateral_wallet_id_wallets",
        "credit_card_accounts",
        type_="foreignkey",
    )
    op.drop_column("credit_card_accounts", "collateral_amount")
    op.drop_column("credit_card_accounts", "collateral_wallet_id")
