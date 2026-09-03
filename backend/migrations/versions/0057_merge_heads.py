"""Merge the three heads left after this session's parallel business-account
work: 0054_ai_insight_period_key (unrelated AI-insight caching work off the
main line), 0055_payment_request_reference (invoice reference/note on
payment requests) and 0056_bulk_transfer_templates (recurring bulk-transfer
templates, itself already on top of 0055_transaction_batch_reference).
Unrelated DDL on all three branches, so this is a plain no-op
reconciliation - same pattern as 0050_merge_heads and 0053_merge_heads.

Revision ID: 0057_merge_heads
Revises: 0054_ai_insight_period_key, 0055_payment_request_reference, 0056_bulk_transfer_templates
Create Date: 2026-09-03
"""
from typing import Sequence, Union

revision: str = "0057_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "0054_ai_insight_period_key",
    "0055_payment_request_reference",
    "0056_bulk_transfer_templates",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
