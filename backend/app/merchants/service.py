"""Merchant catalog and cashback-offer business rules (architecture.md §11).

Cashback is never money back into a wallet — the transaction engine
(app/transactions/service.py, owned by the payments module) has no
purchase-refund path, and this module doesn't mutate wallet balances.
Instead, cashback (card-tier percent + this merchant's own offer percent,
if any — see CARD_TIER_CASHBACK_PERCENT / _earn_from_transaction) is
converted into bonus reward points at POINT_VALUE_IN_RON and credited to
the points balance alongside the base points-per-RON earned on the payment.

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

These values must match frontend/src/config/rewardPolicy.ts's
CARD_TIER_POINTS_PER_RON exactly — that file is the display-side copy of
this same rule (CardsPage.tsx and RewardsPage.tsx both read from it instead
of each hardcoding their own numbers, which is what caused Cards and
Rewards to disagree before). There's no automated check tying the two
together, so change both together by hand.
"""
import secrets
import uuid
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cards.models import CardTier
from app.cards.repository import CardRepository
from app.core.exceptions import NotFoundError, ValidationError
from app.fx.service import FXService
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

# Card-tier cashback (separate from the points-per-RON rate above): a general
# perk of the card itself, applied at any verified partner regardless of
# whether that merchant currently has an active CashbackOffer. Stacks with
# the merchant's own offer percent (CashbackOffer.cashback_percent) rather
# than replacing it — see _earn_from_transaction.
CARD_TIER_CASHBACK_PERCENT: dict[CardTier, Decimal] = {
    CardTier.REGULAR: Decimal("0"),
    CardTier.GOLD: Decimal("2"),
    CardTier.PLATINUM: Decimal("4"),
}

# 1 RON = 20 points, i.e. how cashback (tier + partner, converted to a RON
# amount) turns into bonus points instead of money back into a wallet. Must
# match frontend/src/config/rewardPolicy.ts's POINT_VALUE_IN_RON.
POINT_VALUE_IN_RON = Decimal("0.05")


class MerchantService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MerchantRepository(db)
        self.rewards = RewardsService(db)
        self.transactions = TransactionRepository(db)
        self.cards = CardRepository(db)
        self.fx = FXService(db)

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
            tier = self._card_tier_for(transaction.card_id)

            # The has_earned_for_transaction check above plus this insert isn't
            # atomic, so a concurrent sync for the same user/transaction (e.g. a
            # duplicate effect firing client-side) can race past both checks. The
            # unique constraint on source_transaction_id (migration 0011) is the
            # real guard; a savepoint here means the loser just skips this
            # transaction instead of the whole sync call failing.
            try:
                with self.db.begin_nested():
                    result = self._earn_from_transaction(
                        user_id, merchant, transaction.id, transaction.amount, transaction.currency, today, tier
                    )
            except IntegrityError:
                continue
            results.append(result)
        return results

    def _card_tier_for(self, card_id: uuid.UUID | None) -> CardTier | None:
        if card_id is None:
            return None
        card = self.cards.get_by_id(card_id)
        return card.tier if card is not None else None

    def _earn_from_transaction(
        self,
        user_id: uuid.UUID,
        merchant: Merchant,
        source_transaction_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        today,
        tier: CardTier | None = None,
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
        # scaled by the paying card's tier multiplier. The rule is "points
        # per RON", so a payment from a non-RON wallet must be converted to
        # its RON equivalent first (via FXService, the same deterministic
        # rate table the rest of the app uses for cross-currency math) —
        # otherwise 1 EUR would earn the same points as 1 RON, off by ~5x.
        fx_rate = self.fx.get_rate(currency, "RON")
        amount_in_ron = amount * fx_rate
        multiplier = CARD_TIER_POINT_MULTIPLIER.get(tier, DEFAULT_POINT_MULTIPLIER)
        base_points = int(amount_in_ron * multiplier)

        # Cashback is no longer informational-only: it's two stacking
        # percentages (card-tier perk + this merchant's own offer, if any)
        # converted into bonus points at POINT_VALUE_IN_RON, credited to the
        # points balance the same as base points — never money back into a
        # wallet, and never awarded at all for an unverified merchant (that
        # gate happens one level up, before this method is ever called).
        tier_cashback_percent = CARD_TIER_CASHBACK_PERCENT.get(tier, Decimal("0"))
        tier_cashback_ron = amount_in_ron * tier_cashback_percent / Decimal("100")
        partner_cashback_ron = cashback_amount * fx_rate
        cashback_points = int((tier_cashback_ron + partner_cashback_ron) / POINT_VALUE_IN_RON)

        points_earned = base_points + cashback_points
        proof_code = self._generate_proof_code() if points_earned > 0 else None
        account = (
            self.rewards.earn_points(
                user_id,
                points_earned,
                description=f"Card payment at {merchant.name}",
                source_transaction_id=source_transaction_id,
                proof_code=proof_code,
            )
            if points_earned > 0
            else self.rewards.get_or_create_account(user_id)
        )

        return PurchaseResult(
            merchant_id=merchant.id,
            proof_code=proof_code,
            amount=amount,
            currency=currency,
            cashback_percent=cashback_percent,
            cashback_amount=cashback_amount,
            base_points=base_points,
            cashback_points=cashback_points,
            points_earned=points_earned,
            reward_points_balance=account.points_balance,
        )

    @staticmethod
    def _generate_proof_code() -> str:
        return f"PUR-{secrets.token_hex(4).upper()}"

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
