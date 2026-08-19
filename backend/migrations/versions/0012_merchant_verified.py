"""Add merchants.verified.

Gates reward-point eligibility (MerchantService.sync_purchases_from_transactions)
so an unverified/self-registered merchant can't be paired with a lookalike
counterparty to farm points off fake purchases. Manual for MVP: no approval
workflow, just a flag set at merchant creation (or directly in seed data).

Revision ID: 0012_merchant_verified
Revises: 0011_reward_tx_unique
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_merchant_verified"
down_revision: Union[str, None] = "0011_reward_tx_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "merchants",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("merchants", "verified")
