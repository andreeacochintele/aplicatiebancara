"""Add CHECK constraints so a wallet's balances can never go negative at the
DB level — a backstop behind the SELECT ... FOR UPDATE row locking added in
TransactionService, not a replacement for it (this only catches a bug that
writes a bad value; it can't prevent two racing reads from both computing
one).

Revision ID: 0042_wallet_balance_nonnegative
Revises: 0041_iban_easy_backfill
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0042_wallet_balance_nonnegative"
down_revision: Union[str, None] = "0041_iban_easy_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_wallets_available_balance_nonnegative", "wallets", "available_balance >= 0"
    )
    op.create_check_constraint(
        "ck_wallets_reserved_balance_nonnegative", "wallets", "reserved_balance >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_wallets_reserved_balance_nonnegative", "wallets", type_="check")
    op.drop_constraint("ck_wallets_available_balance_nonnegative", "wallets", type_="check")
