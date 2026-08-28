"""Allow a user to hold more than one wallet in the same currency: drop
UNIQUE(user_id, currency), add a nickname column so same-currency wallets
can be told apart in the UI (e.g. "RON - Savings" / "RON - Spending").

Revision ID: 0045_wallet_nickname_multi_currency
Revises: 0044_business_profiles
Create Date: 2026-08-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045_wallet_nickname_multi_currency"
down_revision: Union[str, None] = "0044_business_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_wallet_user_currency", "wallets", type_="unique")
    op.add_column("wallets", sa.Column("nickname", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("wallets", "nickname")
    op.create_unique_constraint("uq_wallet_user_currency", "wallets", ["user_id", "currency"])
