"""Add reward_accounts.referral_code and reward_transactions.proof_code.

Both are real, unique, generated (secrets.token_hex) codes — referral_code
lazily on first read of a reward account, proof_code when a real merchant
purchase earns points. Only the surrounding flows (validating a referred
friend, awarding 500 pts) are still mock; the codes themselves aren't.

Revision ID: 0019_referral_and_proof_codes
Revises: 0018_merge_heads
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_referral_and_proof_codes"
down_revision: Union[str, None] = "0018_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reward_accounts", sa.Column("referral_code", sa.String(20), nullable=True))
    op.create_unique_constraint("uq_reward_accounts_referral_code", "reward_accounts", ["referral_code"])
    op.add_column("reward_transactions", sa.Column("proof_code", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("reward_transactions", "proof_code")
    op.drop_constraint("uq_reward_accounts_referral_code", "reward_accounts", type_="unique")
    op.drop_column("reward_accounts", "referral_code")
