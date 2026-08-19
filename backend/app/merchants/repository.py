"""Data-access layer for Merchant and CashbackOffer."""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.merchants.models import CashbackOffer, CashbackOfferStatus, Merchant, MerchantStatus


class MerchantRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, merchant: Merchant) -> Merchant:
        self.db.add(merchant)
        self.db.flush()
        return merchant

    def get_by_id(self, merchant_id: uuid.UUID) -> Merchant | None:
        return self.db.get(Merchant, merchant_id)

    def list_active(self) -> list[Merchant]:
        stmt = select(Merchant).where(Merchant.status == MerchantStatus.ACTIVE)
        return list(self.db.scalars(stmt))

    def add_offer(self, offer: CashbackOffer) -> CashbackOffer:
        self.db.add(offer)
        self.db.flush()
        return offer

    def active_offer_for_merchant(self, merchant_id: uuid.UUID, today: date) -> CashbackOffer | None:
        stmt = select(CashbackOffer).where(
            CashbackOffer.merchant_id == merchant_id,
            CashbackOffer.status == CashbackOfferStatus.ACTIVE,
            CashbackOffer.start_date <= today,
            CashbackOffer.end_date >= today,
        )
        return self.db.scalars(stmt).first()
