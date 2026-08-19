"""Add transactions.card_id.

Records which card a CARD_PAYMENT was made with, same bare-UUID pattern as
merchant_id (no FK — transactions/ doesn't take a hard dependency on
app/cards). MerchantService.sync_purchases_from_transactions reads it to look
up the card's tier and scale reward points accordingly.

Revision ID: 0015_transaction_card_id
Revises: 0014_merge_cards_rewards
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_transaction_card_id"
down_revision: Union[str, None] = "0014_merge_cards_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "card_id")
