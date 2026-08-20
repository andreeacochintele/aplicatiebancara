"""Merge payments folders and credit currency heads.

Revision ID: 0018_merge_payments_credit
Revises: 0015_bill_splits_folders, 0017_credit_currency
Create Date: 2026-08-20
"""
from typing import Sequence, Union

revision: str = "0018_merge_payments_credit"
down_revision: Union[str, tuple[str, str], None] = ("0015_bill_splits_folders", "0017_credit_currency")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
