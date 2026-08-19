"""Data-access layer for Merchant and CashbackOffer."""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.merchants.models import CashbackOffer, CashbackOfferStatus, Merchant, MerchantStatus
from app.supabase import is_supabase_session


class MerchantRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, merchant: Merchant) -> Merchant:
        if is_supabase_session(self.db):
            return self.db.add(merchant)
        self.db.add(merchant)
        self.db.flush()
        return merchant

    def get_by_id(self, merchant_id: uuid.UUID) -> Merchant | None:
        if is_supabase_session(self.db):
            return self.db.get(Merchant, merchant_id)
        return self.db.get(Merchant, merchant_id)

    def list_active(self) -> list[Merchant]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(Merchant, {"status": f"eq.{MerchantStatus.ACTIVE.value}", "order": "name.asc"})
        stmt = select(Merchant).where(Merchant.status == MerchantStatus.ACTIVE)
        return list(self.db.scalars(stmt))

    def add_offer(self, offer: CashbackOffer) -> CashbackOffer:
        if is_supabase_session(self.db):
            return self.db.add(offer)
        self.db.add(offer)
        self.db.flush()
        return offer

    def active_offer_for_merchant(self, merchant_id: uuid.UUID, today: date) -> CashbackOffer | None:
        if is_supabase_session(self.db):
            offers = self.db.fetch_many(
                CashbackOffer,
                {
                    "merchant_id": f"eq.{merchant_id}",
                    "status": f"eq.{CashbackOfferStatus.ACTIVE.value}",
                    "order": "created_at.desc",
                },
            )
            return next((offer for offer in offers if offer.start_date <= today <= offer.end_date), None)
        stmt = select(CashbackOffer).where(
            CashbackOffer.merchant_id == merchant_id,
            CashbackOffer.status == CashbackOfferStatus.ACTIVE,
            CashbackOffer.start_date <= today,
            CashbackOffer.end_date >= today,
        )
        return self.db.scalars(stmt).first()
