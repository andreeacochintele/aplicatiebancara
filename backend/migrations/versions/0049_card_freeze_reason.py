"""cards.freeze_reason / frozen_at / frozen_by_admin_id.

Additive columns for the fraud-hold card-freeze workflow (fraud/service.py,
cards/service.py): distinguishes a cardholder's own self-service freeze
(USER_REQUESTED) from a freeze the deterministic fraud engine placed
(FRAUD_HOLD), which only an admin can clear via
POST /fraud/cases/{id}/activate-card. All three columns are nullable and
unrelated to any existing column, so this is a pure additive change to the
existing cards table — no backfill needed, every pre-existing row simply
has freeze_reason/frozen_at/frozen_by_admin_id = NULL.

Revision ID: 0049_card_freeze_reason
Revises: 0048_conversation_message_action_id
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_card_freeze_reason"
down_revision: Union[str, None] = "0048_conversation_message_action_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FREEZE_REASON_ENUM = sa.Enum("USER_REQUESTED", "FRAUD_HOLD", name="card_freeze_reason")


def upgrade() -> None:
    _FREEZE_REASON_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column("cards", sa.Column("freeze_reason", _FREEZE_REASON_ENUM, nullable=True))
    op.add_column("cards", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "cards",
        sa.Column("frozen_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cards", "frozen_by_admin_id")
    op.drop_column("cards", "frozen_at")
    op.drop_column("cards", "freeze_reason")
    _FREEZE_REASON_ENUM.drop(op.get_bind(), checkfirst=True)
