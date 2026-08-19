"""Merchant catalog and cashback-offer business rules (architecture.md §11).

Cashback amount computed here is informational math only: crediting money
into a wallet requires the transaction engine (app/transactions/service.py,
owned by the payments module) to post an actual CASHBACK transaction, and
there's no purchase-creation path into that engine yet.

`sync_purchases_from_transactions` awards bank reward points off the user's
*real* completed CARD_PAYMENT transactions instead of a client-supplied
amount — dev4 doesn't own app/transactions or app/cards, so this only ever
reads those tables, the same read-only cross-module pattern app/analytics and
app/budgets already use. The merchant is resolved from Transaction.merchant_id
when it's set (populated by TransactionService.create_card_payment); older
transactions that predate that endpoint (e.g. seed data) fall back to a
name match against the free-text description (e.g. "Nike - Shopping"). Each
transaction earns points at most once via
RewardsService.has_earned_for_transaction (keyed on
RewardTransaction.source_transaction_id).

CARD_TIER_POINT_MULTIPLIER wires up what rewards/service.py's docstring
already flagged as advertised-but-not-implemented: a higher card tier (Dev
3's cards/models.py CardTier, not our own reward tier) earns points faster.
Looked up via Transaction.card_id; missing/unknown card or no tier (e.g. a
ONE_TIME card, or a legacy transaction with no card_id) earns at the 1x
base rate.
"""
import uuid
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cards.models import CardTier
from app.cards.repository import CardRepository
from app.core.exceptions import NotFoundError, ValidationError
from app.merchants.models import CashbackOffer, Merchant, MerchantStatus
from app.merchants.repository import MerchantRepository
from app.merchants.schemas import (
    CashbackOfferCreate,
    CashbackOfferPublic,
    MerchantCreate,
    MerchantPublic,
    PurchaseResult,
)
from app.rewards.service import RewardsService
from app.transactions.models import TransactionStatus, TransactionType
from app.transactions.repository import TransactionRepository

CARD_TIER_POINT_MULTIPLIER: dict[CardTier, Decimal] = {
    CardTier.REGULAR: Decimal("1"),
    CardTier.GOLD: Decimal("1.5"),
    CardTier.PLATINUM: Decimal("2"),
}
DEFAULT_POINT_MULTIPLIER = Decimal("1")


class MerchantService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MerchantRepository(db)
        self.rewards = RewardsService(db)
        self.transactions = TransactionRepository(db)
        self.cards = CardRepository(db)

    def create_merchant(self, data: MerchantCreate) -> MerchantPublic:
        merchant = Merchant(name=data.name, category=data.category, logo_url=data.logo_url, verified=data.verified)
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

    def sync_purchases_from_transactions(self, user_id: uuid.UUID) -> list[PurchaseResult]:
        # Only verified merchants are eligible for reward points — an
        # unverified one could otherwise be paired with a lookalike
        # counterparty to farm points off fake purchases.
        merchants = [m for m in self.repository.list_active() if m.verified]
        if not merchants:
            return []

        today = datetime.now(timezone.utc).date()
        results: list[PurchaseResult] = []
        for transaction in self.transactions.list_for_user(user_id):
            if transaction.type != TransactionType.CARD_PAYMENT or transaction.status != TransactionStatus.COMPLETED:
                continue
            if self.rewards.has_earned_for_transaction(transaction.id):
                continue
            merchant = self._merchant_for(transaction.merchant_id, transaction.description, merchants)
            if merchant is None:
                continue
            multiplier = self._point_multiplier_for(transaction.card_id)

            # The has_earned_for_transaction check above plus this insert isn't
            # atomic, so a concurrent sync for the same user/transaction (e.g. a
            # duplicate effect firing client-side) can race past both checks. The
            # unique constraint on source_transaction_id (migration 0011) is the
            # real guard; a savepoint here means the loser just skips this
            # transaction instead of the whole sync call failing.
            try:
                with self.db.begin_nested():
                    result = self._earn_from_transaction(
                        user_id, merchant, transaction.id, transaction.amount, transaction.currency, today, multiplier
                    )
            except IntegrityError:
                continue
            results.append(result)
        return results

    def _point_multiplier_for(self, card_id: uuid.UUID | None) -> Decimal:
        if card_id is None:
            return DEFAULT_POINT_MULTIPLIER
        card = self.cards.get_by_id(card_id)
        if card is None or card.tier is None:
            return DEFAULT_POINT_MULTIPLIER
        return CARD_TIER_POINT_MULTIPLIER.get(card.tier, DEFAULT_POINT_MULTIPLIER)

    def _earn_from_transaction(
        self,
        user_id: uuid.UUID,
        merchant: Merchant,
        source_transaction_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        today,
        multiplier: Decimal = DEFAULT_POINT_MULTIPLIER,
    ) -> PurchaseResult:
        offer = self.repository.active_offer_for_merchant(merchant.id, today)
        cashback_percent = None
        cashback_amount = Decimal("0")
        if offer is not None and (offer.minimum_spend is None or amount >= offer.minimum_spend):
            cashback_percent = offer.cashback_percent
            cashback_amount = (amount * offer.cashback_percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )
            if offer.maximum_cashback is not None:
                cashback_amount = min(cashback_amount, offer.maximum_cashback)

        # 100 RON spent -> 100 points at the 1x base rate (architecture.md §11),
        # scaled by the paying card's tier multiplier.
        points_earned = int(amount * multiplier)
        account = (
            self.rewards.earn_points(
                user_id,
                points_earned,
                description=f"Card payment at {merchant.name}",
                source_transaction_id=source_transaction_id,
            )
            if points_earned > 0
            else self.rewards.get_or_create_account(user_id)
        )

        return PurchaseResult(
            merchant_id=merchant.id,
            amount=amount,
            currency=currency,
            cashback_percent=cashback_percent,
            cashback_amount=cashback_amount,
            points_earned=points_earned,
            reward_points_balance=account.points_balance,
        )

    @staticmethod
    def _merchant_for(
        merchant_id: uuid.UUID | None, description: str | None, merchants: list[Merchant]
    ) -> Merchant | None:
        if merchant_id is not None:
            return next((m for m in merchants if m.id == merchant_id), None)
        if not description:
            return None
        text = description.lower()
        for merchant in merchants:
            if merchant.name.lower() in text:
                return merchant
        return None

    def _to_public(self, merchant: Merchant) -> MerchantPublic:
        offer = self.repository.active_offer_for_merchant(merchant.id, datetime.now(timezone.utc).date())
        return MerchantPublic(
            id=merchant.id,
            name=merchant.name,
            category=merchant.category,
            logo_url=merchant.logo_url,
            status=merchant.status,
            verified=merchant.verified,
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
