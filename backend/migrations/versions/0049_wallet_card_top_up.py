"""Add TOP_UP to transaction_type for the mock card top-up flow.

Adds TOP_UP to transaction_type — the wallet "Add money" feature credits a
wallet from a user's own mock EasyB card, backed by a real Transaction +
WalletLedgerEntry like every other money movement, instead of a separate
un-ledgered mutation.

Revision ID: 0049_wallet_card_top_up
Revises: 0048_conversation_message_action_id
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0049_wallet_card_top_up"
down_revision: Union[str, None] = "0048_conversation_message_action_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'TOP_UP'")


def downgrade() -> None:
    # transaction_type's new value is intentionally not removed on
    # downgrade — Postgres cannot drop individual enum values.
    pass
