"""Add fraud_cases.batch_reference — lets the admin Fraud Review page group
and decide together every case created from the same bulk-transfer submit
(IbanTransferService.create_bulk_transfer), instead of one unrelated-looking
case per row.

Revision ID: 0054_fraud_case_batch_reference
Revises: 0053_merge_heads
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_fraud_case_batch_reference"
down_revision: Union[str, None] = "0053_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fraud_cases", sa.Column("batch_reference", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("fraud_cases", "batch_reference")
