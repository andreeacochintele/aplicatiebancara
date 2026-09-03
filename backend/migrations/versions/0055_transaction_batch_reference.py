"""Add transactions.batch_reference — lets the Bulk Transfer page list past
batches (IbanTransferService.create_bulk_transfer), since most rows never
create a FraudCase (fraud_cases.batch_reference, migration 0054) to carry
that value on.

Revision ID: 0055_transaction_batch_reference
Revises: 0054_fraud_case_batch_reference
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_transaction_batch_reference"
down_revision: Union[str, None] = "0054_fraud_case_batch_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("batch_reference", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "batch_reference")
