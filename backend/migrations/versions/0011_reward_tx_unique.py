"""Unique constraint on reward_transactions.source_transaction_id.

MerchantService.sync_purchases_from_transactions (feature/dev4/rewards-cashback)
awards points for a real CARD_PAYMENT transaction by checking
"is there already a reward_transaction with this source_transaction_id"
before inserting one. Without a DB constraint that check-then-insert isn't
atomic: two concurrent syncs for the same user (e.g. React firing the sync
effect twice) can both pass the check and both insert, double-crediting
points for one real payment. Postgres treats NULLs as distinct under a plain
UNIQUE constraint, so this doesn't affect the many reward_transactions rows
that aren't tied to a source transaction (manual earns/redeems, benefit
redemptions).

Revision ID: 0011_reward_tx_unique
Revises: 0010_merge_rewards
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011_reward_tx_unique"
down_revision: Union[str, None] = "0010_merge_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_reward_transactions_source_transaction_id",
        "reward_transactions",
        ["source_transaction_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_reward_transactions_source_transaction_id",
        "reward_transactions",
        type_="unique",
    )
