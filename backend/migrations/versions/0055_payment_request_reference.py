"""Add payment_requests.reference/note — lets a payment request be sent as
an invoice (a reference number + a note), purely descriptive, never used in
payment logic.

Note: this branches off 0054 in parallel with another branch's own 0055
(0055_transaction_batch_reference) — both add an unrelated nullable column
on a different table, so once merged they'll need a plain no-op merge
migration, same pattern as every earlier reconciliation in this history.

Revision ID: 0055_payment_request_reference
Revises: 0054_fraud_case_batch_reference
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_payment_request_reference"
down_revision: Union[str, None] = "0054_fraud_case_batch_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_requests", sa.Column("reference", sa.String(length=50), nullable=True))
    op.add_column("payment_requests", sa.Column("note", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("payment_requests", "note")
    op.drop_column("payment_requests", "reference")
