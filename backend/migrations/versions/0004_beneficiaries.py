"""Beneficiaries for saved payment recipients.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "beneficiaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("beneficiary_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_beneficiaries_owner_user_id", "beneficiaries", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_beneficiaries_owner_user_id", table_name="beneficiaries")
    op.drop_table("beneficiaries")
