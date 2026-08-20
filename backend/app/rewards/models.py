"""RewardAccount and RewardTransaction — bank reward points ledger (architecture.md §11).

Points track spend-driven rewards independent of wallet money — the same
simplification `savings_goals.current_amount` already uses (see
app/savings/models.py): nothing here moves real wallet balance, which stays
owned by the transaction engine in app/transactions/service.py.

RewardBenefit is a points-redeemable perks catalog. There is deliberately no
separate "membership plan"/reward-tier layer above the cards a user owns —
that concept (formerly RewardTier: STANDARD/PREMIUM/METAL, auto-unlocked
from lifetime points) was removed because it duplicated app/cards'
CardTier (REGULAR/GOLD/PLATINUM) without a clear relationship between the
two. A benefit's gate, if any, is `min_card_tier` — owning at least one card
of that tier, checked against app/cards' CardTier directly.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.cards.models import CardTier
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


class RewardBenefit(Base):
    __tablename__ = "reward_benefits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[BenefitCategory] = mapped_column(Enum(BenefitCategory, name="benefit_category"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    points_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_card_tier: Mapped[CardTier | None] = mapped_column(Enum(CardTier, name="card_tier"), nullable=True)
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
    # Which card the user chose to "pay" with at redemption — receipt/audit
    # only, same bare-UUID no-FK pattern as transactions.card_id. Doesn't
    # change how future points are earned.
    card_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    redemption_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    points_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    benefit = relationship("RewardBenefit")
