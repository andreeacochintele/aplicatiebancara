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


class CardFreezeReason(str, enum.Enum):
    """Why a FROZEN card is frozen. USER_REQUESTED is the cardholder's own
    self-service freeze (cards/router.py's PATCH /freeze); FRAUD_HOLD is set
    only by FraudService when a payment on this card crosses the fraud
    threshold (fraud/service.py) and can only be cleared by an admin via
    POST /fraud/cases/{id}/activate-card — the cardholder's own unfreeze
    endpoint refuses while this reason is set. Null whenever status is not
    FROZEN."""

    USER_REQUESTED = "USER_REQUESTED"
    FRAUD_HOLD = "FRAUD_HOLD"


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
    freeze_reason: Mapped[CardFreezeReason | None] = mapped_column(
        Enum(CardFreezeReason, name="card_freeze_reason"), nullable=True
    )
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The admin who last cleared a FRAUD_HOLD via activate-card (see
    # CardFreezeReason docstring) — never set for a USER_REQUESTED freeze,
    # since that's the cardholder acting on their own card, not an admin
    # action. Kept alongside admin_audit_logs (the authoritative record of
    # who/when/why) purely so a card row can answer "which admin last
    # reactivated this" without a join.
    frozen_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    masked_pan: Mapped[str] = mapped_column(String(19), nullable=False)
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    mock_pan: Mapped[str] = mapped_column(String(19), nullable=False)
    mock_cvv: Mapped[str] = mapped_column(String(3), nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expiration_month: Mapped[int] = mapped_column(Integer, nullable=False)
    expiration_year: Mapped[int] = mapped_column(Integer, nullable=False)
    one_time_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Explicit foreign_keys: frozen_by_admin_id (added alongside freeze_reason
    # above) is a second FK from this table to users.id, so SQLAlchemy can no
    # longer infer which column this relationship should join on.
    owner = relationship("User", foreign_keys=[user_id])
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

    @property
    def has_pin(self) -> bool:
        override = getattr(self, "_has_pin_override", None)
        if override is not None:
            return bool(override)
        return bool(self.pin_hash)

    @has_pin.setter
    def has_pin(self, value: bool) -> None:
        self._has_pin_override = bool(value)


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
