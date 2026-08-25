"""Merge the two parallel heads left after PR #47 (credit documents:
0030_backfill_credit_currency_and_dates -> 0031_credit_documents ->
0032_credit_document_content) and PR #48 (fraud/AI:
0030_fraud_unusual_time -> 0031_ai_conversations), both branched from
0029_ai_conversation_messages independently. Unrelated DDL on both sides,
so this is a plain no-op reconciliation.

Revision ID: 0033_merge_heads
Revises: 0032_credit_document_content, 0031_ai_conversations
Create Date: 2026-08-25
"""
from typing import Sequence, Union

revision: str = "0033_merge_heads"
down_revision: Union[str, tuple[str, str], None] = ("0032_credit_document_content", "0031_ai_conversations")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
