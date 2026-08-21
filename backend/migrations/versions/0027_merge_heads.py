"""Merge the two parallel 0026 heads: 0026_credit_card_accounts (stored
credit card balances) and 0026_fraud_cases (deterministic fraud engine
output), both branched from 0025_merge_heads.

Revision ID: 0027_merge_heads
Revises: 0026_credit_card_accounts, 0026_fraud_cases
Create Date: 2026-08-21
"""
from typing import Sequence, Union

revision: str = "0027_merge_heads"
down_revision: Union[str, tuple[str, str], None] = ("0026_credit_card_accounts", "0026_fraud_cases")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
