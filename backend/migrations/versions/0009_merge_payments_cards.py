"""Merge payments and cards migration heads.

Revision ID: 0009_merge_payments_cards
Revises: 0006, 0008_loans
Create Date: 2026-08-18
"""
from typing import Sequence, Union

revision: str = "0009_merge_payments_cards"
down_revision: Union[str, tuple[str, str], None] = ("0006", "0008_loans")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
