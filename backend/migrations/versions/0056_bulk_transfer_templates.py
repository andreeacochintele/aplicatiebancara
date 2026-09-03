"""Add bulk_transfer_templates / bulk_transfer_template_rows — a saved
payroll-style batch (payments/service.py's create_bulk_transfer) the owner
can re-run on demand and advance on a schedule. Reuses the existing
scheduled_payment_frequency/scheduled_payment_status enum types rather than
creating new ones.

Revision ID: 0056_bulk_transfer_templates
Revises: 0055_transaction_batch_reference
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056_bulk_transfer_templates"
down_revision: Union[str, None] = "0055_transaction_batch_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    frequency_enum = postgresql.ENUM(
        "ONCE", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY",
        name="scheduled_payment_frequency", create_type=False,
    )
    status_enum = postgresql.ENUM(
        "ACTIVE", "PAUSED", "CANCELLED",
        name="scheduled_payment_status", create_type=False,
    )
    op.create_table(
        "bulk_transfer_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("frequency", frequency_enum, nullable=False),
        sa.Column("next_run_on", sa.Date(), nullable=False),
        sa.Column("status", status_enum, nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_bulk_transfer_templates_owner", "bulk_transfer_templates", ["owner_user_id"]
    )
    op.create_table(
        "bulk_transfer_template_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bulk_transfer_templates.id"),
            nullable=False,
        ),
        sa.Column("beneficiary_name", sa.String(length=255), nullable=False),
        sa.Column("iban", sa.String(length=34), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_bulk_transfer_template_rows_template", "bulk_transfer_template_rows", ["template_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_transfer_template_rows_template", table_name="bulk_transfer_template_rows")
    op.drop_table("bulk_transfer_template_rows")
    op.drop_index("ix_bulk_transfer_templates_owner", table_name="bulk_transfer_templates")
    op.drop_table("bulk_transfer_templates")
