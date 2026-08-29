"""Merge the two heads left after merging master into
feature/fraud/screen-transfers: 0049_wallet_card_top_up (master's wallet
top-up enum value) and 0049_fraud_repeated_transfer_pattern (this branch's
fraud flag enum value), both branched off 0048_conversation_message_action_id
independently. Unrelated DDL on both branches, so this is a plain no-op
reconciliation — same pattern as every earlier merge in this history.

Revision ID: 0050_merge_heads
Revises: 0049_wallet_card_top_up, 0049_fraud_repeated_transfer_pattern
Create Date: 2026-08-29
"""
from typing import Sequence, Union

revision: str = "0050_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "0049_wallet_card_top_up",
    "0049_fraud_repeated_transfer_pattern",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
