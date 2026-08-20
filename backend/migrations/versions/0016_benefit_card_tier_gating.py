"""Replace RewardTier-based benefit gating with min_card_tier.

Team decision: no separate "membership plan" layered on top of card tiers —
rewards should be tied directly to the cards a user owns, not to an
abstract, points-earned status. Drops reward_tiers and
RewardBenefit.min_tier_id, adds RewardBenefit.min_card_tier (reusing the
card_tier enum type from migration 0011_card_tiers) so a benefit can require
owning at least a Gold or Platinum card instead of a reward tier.

Also adds BenefitRedemption.card_id (which card the user picked to "pay"
with at redemption — receipt/audit only, same bare-UUID no-FK pattern as
transactions.card_id) and BenefitRedemption.redemption_code (a mock voucher
code shown to the user as proof of redemption).

Revision ID: 0016_benefit_card_tier_gating
Revises: 0015_transaction_card_id
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_benefit_card_tier_gating"
down_revision: Union[str, None] = "0015_transaction_card_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CARD_TIER = postgresql.ENUM("REGULAR", "GOLD", "PLATINUM", name="card_tier", create_type=False)


def upgrade() -> None:
    op.add_column("reward_benefits", sa.Column("min_card_tier", CARD_TIER, nullable=True))
    op.drop_constraint("reward_benefits_min_tier_id_fkey", "reward_benefits", type_="foreignkey")
    op.drop_column("reward_benefits", "min_tier_id")
    op.drop_table("reward_tiers")

    op.add_column("benefit_redemptions", sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("benefit_redemptions", sa.Column("redemption_code", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("benefit_redemptions", "redemption_code")
    op.drop_column("benefit_redemptions", "card_id")

    op.create_table(
        "reward_tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("min_lifetime_points", sa.Integer(), nullable=False),
        sa.Column("perks", sa.String(1000), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column(
        "reward_benefits",
        sa.Column("min_tier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reward_tiers.id"), nullable=True),
    )
    op.drop_column("reward_benefits", "min_card_tier")
