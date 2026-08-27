"""Add transaction_categories and exports (job history) tables.

Revision ID: 0036_export_jobs_and_categories
Revises: 0035_credit_card_collateral
Create Date: 2026-08-27
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_export_jobs_and_categories"
down_revision: Union[str, None] = "0035_credit_card_collateral"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed starter set — nothing in the app assigns these to a transaction yet
# (see transactions/models.py's TransactionCategory docstring); seeding them
# just means category_id resolves to a real name wherever it IS set.
_DEFAULT_CATEGORIES = [
    "Groceries",
    "Restaurants",
    "Transport",
    "Shopping",
    "Bills",
    "Income",
    "Transfers",
    "Other",
]


def upgrade() -> None:
    op.create_table(
        "transaction_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    categories_table = sa.table(
        "transaction_categories",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
    )
    op.bulk_insert(categories_table, [{"id": str(uuid.uuid4()), "name": name} for name in _DEFAULT_CATEGORIES])

    bind = op.get_bind()
    sa.Enum("STATEMENT", "BUSINESS_TRANSACTIONS", name="export_type").create(bind, checkfirst=True)
    sa.Enum("CSV", "XLSX", "PDF", name="export_format").create(bind, checkfirst=True)
    sa.Enum("PROCESSING", "READY", "FAILED", name="export_status").create(bind, checkfirst=True)

    export_type = postgresql.ENUM("STATEMENT", "BUSINESS_TRANSACTIONS", name="export_type", create_type=False)
    export_format = postgresql.ENUM("CSV", "XLSX", "PDF", name="export_format", create_type=False)
    export_status = postgresql.ENUM("PROCESSING", "READY", "FAILED", name="export_status", create_type=False)

    op.create_table(
        "exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", export_type, nullable=False),
        sa.Column("format", export_format, nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column("status", export_status, nullable=False, server_default="READY"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_exports_user_id", "exports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_exports_user_id", table_name="exports")
    op.drop_table("exports")
    sa.Enum(name="export_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="export_format").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="export_type").drop(op.get_bind(), checkfirst=True)
    op.drop_table("transaction_categories")
