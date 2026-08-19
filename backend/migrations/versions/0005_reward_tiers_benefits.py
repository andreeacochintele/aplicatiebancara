"""Reward tiers and points-redeemable benefits catalog (architecture.md §11 extension).

Adds a Revolut-style layer on top of the 0004 rewards ledger: tiers
(STANDARD/PREMIUM/METAL) auto-unlock from lifetime points earned, and a
benefits catalog (lounge access, retail discounts, travel perks, ...) can be
redeemed with points, optionally gated by tier.

Revision ID: 0005_reward_tiers_benefits
Revises: 0004_merchants_rewards
Create Date: 2026-08-18

Renamed from the plain "0005" during a merge with master, following
0004_merchants_rewards' rename — see that file for why.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_reward_tiers_benefits"
down_revision: Union[str, None] = "0004_merchants_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIERS = [
    ("STANDARD", 0, "Earn 1 point per RON spent|Redeem points in the benefits catalog", 0),
    ("PREMIUM", 2000, "Airport lounge access|Priority customer support|Early access to new cashback offers", 1),
    ("METAL", 8000, "Unlimited airport lounge access|Dedicated concierge support|Premium travel insurance", 2),
]


def upgrade() -> None:
    op.add_column(
        "reward_accounts",
        sa.Column("lifetime_points_earned", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "reward_tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("min_lifetime_points", sa.Integer(), nullable=False),
        sa.Column("perks", sa.String(1000), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "reward_benefits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column(
            "category",
            sa.Enum("LOUNGE_ACCESS", "RETAIL_DISCOUNT", "TRAVEL", "INSURANCE", "OTHER", name="benefit_category"),
            nullable=False,
        ),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("points_cost", sa.Integer(), nullable=True),
        sa.Column("min_tier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reward_tiers.id"), nullable=True),
        sa.Column("partner_name", sa.String(150), nullable=True),
        sa.Column(
            "status", sa.Enum("ACTIVE", "INACTIVE", name="benefit_status"), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "benefit_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reward_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reward_accounts.id"), nullable=False
        ),
        sa.Column("benefit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reward_benefits.id"), nullable=False),
        sa.Column(
            "reward_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reward_transactions.id"),
            nullable=True,
        ),
        sa.Column("points_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    reward_tiers_table = sa.table(
        "reward_tiers",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("min_lifetime_points", sa.Integer),
        sa.column("perks", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        reward_tiers_table,
        [
            {"id": uuid.uuid4(), "name": name, "min_lifetime_points": min_points, "perks": perks, "sort_order": order}
            for name, min_points, perks, order in TIERS
        ],
    )


def downgrade() -> None:
    op.drop_table("benefit_redemptions")

    op.drop_table("reward_benefits")
    sa.Enum(name="benefit_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="benefit_category").drop(op.get_bind(), checkfirst=True)

    op.drop_table("reward_tiers")

    op.drop_column("reward_accounts", "lifetime_points_earned")
