"""Cards domain models.

Cards are mock payment instruments only. They store safe display data and
sandbox-only mock PAN/CVV values, never real card credentials.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class CardType(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    ONE_TIME = "ONE_TIME"


class CardTier(str, enum.Enum):
    REGULAR = "REGULAR"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


class CardStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    default_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True
    )

    type: Mapped[CardType] = mapped_column(Enum(CardType, name="card_type"), nullable=False)
    tier: Mapped[CardTier | None] = mapped_column(Enum(CardTier, name="card_tier"), nullable=True)
    status: Mapped[CardStatus] = mapped_column(
        Enum(CardStatus, name="card_status"), default=CardStatus.ACTIVE, nullable=False
    )

    masked_pan: Mapped[str] = mapped_column(String(19), nullable=False)
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    mock_pan: Mapped[str] = mapped_column(String(19), nullable=False)
    mock_cvv: Mapped[str] = mapped_column(String(3), nullable=False)
    expiration_month: Mapped[int] = mapped_column(Integer, nullable=False)
    expiration_year: Mapped[int] = mapped_column(Integer, nullable=False)
    one_time_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner = relationship("User")
    default_wallet = relationship("Wallet")
    payment_preferences = relationship(
        "CardPaymentPreferences",
        back_populates="card",
        cascade="all, delete-orphan",
        uselist=False,
    )
    credit_account = relationship(
        "CreditCardAccount",
        back_populates="card",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CardPaymentPreferences(Base):
    __tablename__ = "card_payment_preferences"

    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        primary_key=True,
    )
    preferred_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True
    )
    allow_main_wallet_fx: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    card = relationship("Card", back_populates="payment_preferences")
    preferred_wallet = relationship("Wallet")


class CreditCardAccount(Base):
    __tablename__ = "credit_card_accounts"

    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RON", nullable=False)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    used_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    collateral_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True
    )
    collateral_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    card = relationship("Card", back_populates="credit_account")
    owner = relationship("User")
    collateral_wallet = relationship("Wallet")

    @property
    def available_credit(self) -> Decimal:
        return max(Decimal("0.00"), self.credit_limit - self.used_amount)
