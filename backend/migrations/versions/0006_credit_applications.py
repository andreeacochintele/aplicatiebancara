"""Credit applications.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "type",
            sa.Enum("PERSONAL_LOAN", "CREDIT_CARD", name="credit_application_type"),
            nullable=False,
        ),
        sa.Column("requested_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("requested_term_months", sa.Integer(), nullable=True),
        sa.Column("offered_interest_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("offered_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("credit_score_at_application", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "PENDING", "APPROVED", "REJECTED", name="credit_application_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("credit_applications")
    sa.Enum(name="credit_application_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="credit_application_type").drop(op.get_bind(), checkfirst=True)
