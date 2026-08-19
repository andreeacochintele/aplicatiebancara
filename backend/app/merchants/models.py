"""Merchant and CashbackOffer — mock merchant catalog with cashback offers (architecture.md §11).

Cashback here stays informational math (see MerchantService.record_purchase):
actually crediting money into a wallet as a CASHBACK transaction would need
the transaction engine (app/transactions/service.py, owned by the payments
module) to gain a purchase-creation path, which doesn't exist yet.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class MerchantStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class CashbackOfferStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[MerchantStatus] = mapped_column(
        Enum(MerchantStatus, name="merchant_status"), default=MerchantStatus.ACTIVE, nullable=False
    )
    # Gates reward-point eligibility (MerchantService._match_merchant) so an
    # unverified/self-registered "merchant" can't be paired with a lookalike
    # counterparty to farm points off fake purchases. Manual for MVP — no
    # approval workflow yet.
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CashbackOffer(Base):
    __tablename__ = "cashback_offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    cashback_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    maximum_cashback: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    minimum_spend: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[CashbackOfferStatus] = mapped_column(
        Enum(CashbackOfferStatus, name="cashback_offer_status"), default=CashbackOfferStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
