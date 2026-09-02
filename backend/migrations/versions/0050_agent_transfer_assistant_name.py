"""Backfill agent-executed transfer descriptions from "asistent AI" to
"asistent Nova".

Transfers the Actions Agent executed before the rename still carry the
generic "(asistent AI)" suffix in their description (see
app/ai/actions/service.py, which now writes "(asistent Nova)"). The
description is persisted text, not rendered from a label, so existing rows
keep showing the old wording until they are rewritten — this is the
one-time fix for them, same shape as 0041_iban_easy_backfill.

Scoped to the exact parenthesised suffix rather than a bare "asistent AI"
match, so a user-written description that happens to contain those words is
left alone.

Revision ID: 0050_agent_transfer_assistant_name
Revises: 0049_wallet_card_top_up
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0050_agent_transfer_assistant_name"
down_revision: Union[str, None] = "0049_wallet_card_top_up"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE transactions
        SET description = replace(description, '(asistent AI)', '(asistent Nova)')
        WHERE description LIKE '%(asistent AI)%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE transactions
        SET description = replace(description, '(asistent Nova)', '(asistent AI)')
        WHERE description LIKE '%(asistent Nova)%'
        """
    )
