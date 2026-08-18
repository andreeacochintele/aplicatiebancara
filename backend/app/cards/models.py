"""Cards domain models.

Cards are mock payment instruments only. They store safe display data such as
masked PAN/last four, never real PAN or CVV values.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class CardType(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    ONE_TIME = "ONE_TIME"


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
    status: Mapped[CardStatus] = mapped_column(
        Enum(CardStatus, name="card_status"), default=CardStatus.ACTIVE, nullable=False
    )

    masked_pan: Mapped[str] = mapped_column(String(19), nullable=False)
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
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


class CardPaymentPreferences(Base):
    __tablename__ = "card_payment_preferences"

    card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cards.id"), primary_key=True)
    preferred_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True
    )
    allow_main_wallet_fx: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    card = relationship("Card", back_populates="payment_preferences")
    preferred_wallet = relationship("Wallet")
