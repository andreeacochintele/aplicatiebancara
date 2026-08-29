"""Add REPEATED_TRANSFER_PATTERN to fraud_flag_code — the transfer-side
counterpart of REWARD_ABUSE_PATTERN, fired when the fraud engine sees
repeated near-identical transfers to the same destination wallet (see
fraud/service.py).

Additive only: existing fraud_flags rows are untouched and every previously
valid code stays valid.

Revision ID: 0049_fraud_repeated_transfer_pattern
Revises: 0048_conversation_message_action_id
Create Date: 2026-08-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0049_fraud_repeated_transfer_pattern"
down_revision: Union[str, None] = "0048_conversation_message_action_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE fraud_flag_code ADD VALUE IF NOT EXISTS 'REPEATED_TRANSFER_PATTERN'")


def downgrade() -> None:
    # Same reasoning as 0030_fraud_unusual_time: Postgres has no DROP VALUE
    # for enums, and rebuilding fraud_flag_code without this value would mean
    # remapping any fraud_flags rows already using it. Out of scope here.
    pass
