"""Merchant catalog and cashback-offer business rules (architecture.md §11).

Cashback amount computed here is informational math only: crediting money
into a wallet requires the transaction engine (app/transactions/service.py,
owned by the payments module) to post an actual CASHBACK transaction, and
there's no purchase-creation path into that engine yet. `record_purchase`
instead awards bank reward points 1:1 with the spent amount through
RewardsService — the same simplification budgets/savings already use for
numbers that aren't reconciled against the wallet ledger.
"""
import uuid
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.merchants.models import CashbackOffer, Merchant, MerchantStatus
from app.merchants.repository import MerchantRepository
from app.merchants.schemas import (
    CashbackOfferCreate,
    CashbackOfferPublic,
    MerchantCreate,
    MerchantPublic,
    PurchaseCreate,
    PurchaseResult,
)
from app.rewards.service import RewardsService


class MerchantService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MerchantRepository(db)
        self.rewards = RewardsService(db)

    def create_merchant(self, data: MerchantCreate) -> MerchantPublic:
        merchant = Merchant(name=data.name, category=data.category, logo_url=data.logo_url)
        self.repository.add(merchant)
        return self._to_public(merchant)

    def create_cashback_offer(self, merchant_id: uuid.UUID, data: CashbackOfferCreate) -> CashbackOfferPublic:
        merchant = self.repository.get_by_id(merchant_id)
        if merchant is None:
            raise NotFoundError("Merchant not found")
        if data.cashback_percent <= 0:
            raise ValidationError("cashback_percent must be positive")
        if data.end_date < data.start_date:
            raise ValidationError("end_date cannot be before start_date")

        offer = CashbackOffer(
            merchant_id=merchant_id,
            cashback_percent=data.cashback_percent,
            maximum_cashback=data.maximum_cashback,
            minimum_spend=data.minimum_spend,
            start_date=data.start_date,
            end_date=data.end_date,
        )
        self.repository.add_offer(offer)
        return self._offer_to_public(offer)

    def list_merchants(self) -> list[MerchantPublic]:
        return [self._to_public(merchant) for merchant in self.repository.list_active()]

    def get_merchant(self, merchant_id: uuid.UUID) -> MerchantPublic:
        merchant = self.repository.get_by_id(merchant_id)
        if merchant is None:
            raise NotFoundError("Merchant not found")
        return self._to_public(merchant)

    def record_purchase(self, user_id: uuid.UUID, merchant_id: uuid.UUID, data: PurchaseCreate) -> PurchaseResult:
        if data.amount <= 0:
            raise ValidationError("amount must be positive")

        merchant = self.repository.get_by_id(merchant_id)
        if merchant is None or merchant.status != MerchantStatus.ACTIVE:
            raise NotFoundError("Merchant not found")

        offer = self.repository.active_offer_for_merchant(merchant_id, datetime.now(timezone.utc).date())
        cashback_percent = None
        cashback_amount = Decimal("0")
        if offer is not None and (offer.minimum_spend is None or data.amount >= offer.minimum_spend):
            cashback_percent = offer.cashback_percent
            cashback_amount = (data.amount * offer.cashback_percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )
            if offer.maximum_cashback is not None:
                cashback_amount = min(cashback_amount, offer.maximum_cashback)

        points_earned = int(data.amount)  # 100 RON spent -> 100 points (architecture.md §11)
        account = (
            self.rewards.earn_points(user_id, points_earned, description=f"Purchase at {merchant.name}")
            if points_earned > 0
            else self.rewards.get_or_create_account(user_id)
        )

        return PurchaseResult(
            merchant_id=merchant.id,
            amount=data.amount,
            currency=data.currency.upper(),
            cashback_percent=cashback_percent,
            cashback_amount=cashback_amount,
            points_earned=points_earned,
            reward_points_balance=account.points_balance,
        )

    def _to_public(self, merchant: Merchant) -> MerchantPublic:
        offer = self.repository.active_offer_for_merchant(merchant.id, datetime.now(timezone.utc).date())
        return MerchantPublic(
            id=merchant.id,
            name=merchant.name,
            category=merchant.category,
            logo_url=merchant.logo_url,
            status=merchant.status,
            active_offer=self._offer_to_public(offer) if offer is not None else None,
            created_at=merchant.created_at,
        )

    def _offer_to_public(self, offer: CashbackOffer) -> CashbackOfferPublic:
        return CashbackOfferPublic(
            id=offer.id,
            cashback_percent=offer.cashback_percent,
            maximum_cashback=offer.maximum_cashback,
            minimum_spend=offer.minimum_spend,
            start_date=offer.start_date,
            end_date=offer.end_date,
            status=offer.status,
        )
