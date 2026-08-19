"""RewardAccount and RewardTransaction — bank reward points ledger (architecture.md §11).

Points track spend-driven rewards independent of wallet money — the same
simplification `savings_goals.current_amount` already uses (see
app/savings/models.py): nothing here moves real wallet balance, which stays
owned by the transaction engine in app/transactions/service.py.

RewardTier/RewardBenefit add a Revolut-style layer on top: tiers auto-unlock
from lifetime points earned (never decreases on redeem, unlike
points_balance), and benefits are a points-redeemable perks catalog gated by
tier and/or points cost.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class RewardTransactionType(str, enum.Enum):
    EARN = "EARN"
    SPEND = "SPEND"
    ADJUSTMENT = "ADJUSTMENT"


class BenefitCategory(str, enum.Enum):
    LOUNGE_ACCESS = "LOUNGE_ACCESS"
    RETAIL_DISCOUNT = "RETAIL_DISCOUNT"
    TRAVEL = "TRAVEL"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class BenefitStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RewardAccount(Base):
    __tablename__ = "reward_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    points_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RewardTransaction(Base):
    __tablename__ = "reward_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reward_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reward_accounts.id"), nullable=False
    )
    source_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, unique=True
    )
    type: Mapped[RewardTransactionType] = mapped_column(
        Enum(RewardTransactionType, name="reward_transaction_type"), nullable=False
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RewardTier(Base):
    """Reference/config data — rows are seeded by migration 0005, not user-created."""

    __tablename__ = "reward_tiers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    min_lifetime_points: Mapped[int] = mapped_column(Integer, nullable=False)
    perks: Mapped[str] = mapped_column(String(1000), nullable=False)  # "|"-delimited list
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RewardBenefit(Base):
    __tablename__ = "reward_benefits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[BenefitCategory] = mapped_column(Enum(BenefitCategory, name="benefit_category"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    points_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_tier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reward_tiers.id"), nullable=True
    )
    partner_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[BenefitStatus] = mapped_column(
        Enum(BenefitStatus, name="benefit_status"), default=BenefitStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenefitRedemption(Base):
    __tablename__ = "benefit_redemptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reward_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reward_accounts.id"), nullable=False
    )
    benefit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reward_benefits.id"), nullable=False)
    reward_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reward_transactions.id"), nullable=True
    )
    points_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    benefit = relationship("RewardBenefit")
