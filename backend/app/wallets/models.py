"""Wallet — one of the four core domain entities (architecture.md §5, §34).

Supports multiple currencies per user (UNIQUE(user_id, currency)), one main
wallet, and separate available/reserved balances (reserved_balance backs
fraud HOLDs, see WalletLedgerEntry). FX-payment support is delivered on top
of this model by the fx module in a later phase.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow
from app.wallets.iban import generate_iban


class WalletStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_wallet_user_currency"),
        CheckConstraint("available_balance >= 0", name="ck_wallets_available_balance_nonnegative"),
        CheckConstraint("reserved_balance >= 0", name="ck_wallets_reserved_balance_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    iban: Mapped[str] = mapped_column(String(34), unique=True, nullable=False, default=generate_iban)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    reserved_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[WalletStatus] = mapped_column(
        Enum(WalletStatus, name="wallet_status"), default=WalletStatus.ACTIVE, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner = relationship("User", back_populates="wallets")
    ledger_entries = relationship("WalletLedgerEntry", back_populates="wallet")
