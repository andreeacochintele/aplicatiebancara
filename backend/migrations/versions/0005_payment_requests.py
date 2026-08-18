"""Payment requests for QR payments.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("creator_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "destination_wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "PAID", "CANCELLED", "EXPIRED", name="payment_request_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_payment_requests_creator_user_id", "payment_requests", ["creator_user_id"])
    op.create_index("ix_payment_requests_destination_wallet_id", "payment_requests", ["destination_wallet_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_requests_destination_wallet_id", table_name="payment_requests")
    op.drop_index("ix_payment_requests_creator_user_id", table_name="payment_requests")
    op.drop_table("payment_requests")
    sa.Enum(name="payment_request_status").drop(op.get_bind(), checkfirst=True)
