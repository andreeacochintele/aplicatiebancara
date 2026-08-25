"""Add UNUSUAL_TIME to fraud_flag_code — brings back a flag that was in the
original fraud engine design but dropped without being implemented (see
fraud/service.py).

Revision ID: 0030_fraud_unusual_time
Revises: 0029_ai_conversation_messages
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_fraud_unusual_time"
down_revision: Union[str, None] = "0029_ai_conversation_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE fraud_flag_code ADD VALUE IF NOT EXISTS 'UNUSUAL_TIME'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; downgrading this one safely would
    # mean rebuilding fraud_flag_code without UNUSUAL_TIME and remapping any
    # rows using it, which is out of scope for this migration.
    pass
