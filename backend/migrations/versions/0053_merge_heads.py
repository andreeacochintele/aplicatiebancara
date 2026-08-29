"""Merge the three heads left after merging master into test:
0049_card_freeze_reason (this branch's cards.freeze_reason work, branched
off 0048_conversation_message_action_id), 0052_unify_transaction_categories
(tip of master's main line), and 0050_merge_heads (a pre-existing dangling
head already on master before this merge — 0050_agent_transfer_assistant_name
branched off 0049_wallet_card_top_up directly instead of off
0050_merge_heads, so that reconciliation was never actually continued from;
not introduced by this branch, but left unresolved it would still leave
`alembic upgrade head` ambiguous after this merge, so it's folded in here
too). Unrelated DDL on all three branches, so this is a plain no-op
reconciliation — same pattern as every earlier merge in this history.

Revision ID: 0053_merge_heads
Revises: 0049_card_freeze_reason, 0050_merge_heads, 0052_unify_transaction_categories
Create Date: 2026-08-29
"""
from typing import Sequence, Union

revision: str = "0053_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "0049_card_freeze_reason",
    "0050_merge_heads",
    "0052_unify_transaction_categories",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
