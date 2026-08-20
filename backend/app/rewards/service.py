"""Bank reward points ledger and benefits catalog (architecture.md §11).

`earn_points` is also called from app.merchants.service when a real card
payment is synced — it's the one place a caller other than this module's
own router is allowed to credit points.

`RewardAccount.lifetime_points_earned` only ever grows (unlike
`points_balance`, which drops on redeem) — a running stat, not tied to any
gating logic.

Benefits are gated by `min_card_tier` (app/cards' CardTier — REGULAR/GOLD/
PLATINUM), read read-only via CardRepository, the same cross-module pattern
app/merchants already uses to check card tier for point multipliers. There
is deliberately no separate reward-tier/plan concept above that — see the
module docstring in app/rewards/models.py for why.
"""
import secrets
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import DetachedInstanceError

from app.cards.models import CardTier
from app.cards.repository import CardRepository
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.rewards.models import (
    BenefitRedemption,
    BenefitStatus,
    RewardAccount,
    RewardBenefit,
    RewardTransaction,
    RewardTransactionType,
)
from app.rewards.repository import RewardsRepository
from app.rewards.schemas import (
    BenefitRedemptionPublic,
    RewardAccountPublic,
    RewardBenefitPublic,
    RewardTransactionPublic,
)

CARD_TIER_RANK: dict[CardTier, int] = {
    CardTier.REGULAR: 0,
    CardTier.GOLD: 1,
    CardTier.PLATINUM: 2,
}


class RewardsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = RewardsRepository(db)
        self.cards = CardRepository(db)

    def get_or_create_account(self, user_id: uuid.UUID) -> RewardAccount:
        account = self.repository.get_account_for_user(user_id)
        if account is None:
            account = self.repository.add_account(RewardAccount(user_id=user_id))
        return account

    def get_account(self, user_id: uuid.UUID) -> RewardAccountPublic:
        account = self.get_or_create_account(user_id)
        return self._account_to_public(account)

    def earn_points(
        self,
        user_id: uuid.UUID,
        points: int,
        description: str | None = None,
        source_transaction_id: uuid.UUID | None = None,
    ) -> RewardAccount:
        if points <= 0:
            raise ValidationError("points must be positive")

        account = self.get_or_create_account(user_id)
        account.points_balance += points
        account.lifetime_points_earned += points
        self.repository.add_transaction(
            RewardTransaction(
                reward_account_id=account.id,
                source_transaction_id=source_transaction_id,
                type=RewardTransactionType.EARN,
                points=points,
                description=description,
            )
        )
        self.db.flush()
        return account

    def has_earned_for_transaction(self, source_transaction_id: uuid.UUID) -> bool:
        return self.repository.has_transaction_for_source(source_transaction_id)

    def redeem_points(self, user_id: uuid.UUID, points: int) -> RewardAccountPublic:
        if points <= 0:
            raise ValidationError("points must be positive")

        account = self.get_or_create_account(user_id)
        if account.points_balance < points:
            raise ConflictError("Insufficient reward points balance")

        account.points_balance -= points
        self.repository.add_transaction(
            RewardTransaction(
                reward_account_id=account.id,
                type=RewardTransactionType.SPEND,
                points=-points,
                description="Redeemed",
            )
        )
        self.db.flush()
        return self.get_account(user_id)

    def list_benefits(self, user_id: uuid.UUID) -> list[RewardBenefitPublic]:
        account = self.get_or_create_account(user_id)
        best_owned_tier = self._best_owned_card_tier(user_id)

        result = []
        for benefit in self.repository.list_active_benefits():
            locked_reason = None
            if benefit.min_card_tier is not None and not self._meets_card_tier(best_owned_tier, benefit.min_card_tier):
                locked_reason = f"Requires a {benefit.min_card_tier.value.title()} card"
            elif benefit.points_cost is not None and account.points_balance < benefit.points_cost:
                locked_reason = "Not enough points"

            result.append(
                RewardBenefitPublic(
                    id=benefit.id,
                    name=benefit.name,
                    category=benefit.category,
                    description=benefit.description,
                    points_cost=benefit.points_cost,
                    min_card_tier=benefit.min_card_tier,
                    partner_name=benefit.partner_name,
                    can_redeem=locked_reason is None,
                    reason_if_locked=locked_reason,
                )
            )
        return result

    def redeem_benefit(self, user_id: uuid.UUID, benefit_id: uuid.UUID, card_id: uuid.UUID) -> RewardAccountPublic:
        account = self.get_or_create_account(user_id)
        benefit = self.repository.get_benefit(benefit_id)
        if benefit is None or benefit.status != BenefitStatus.ACTIVE:
            raise NotFoundError("Benefit not found")

        card = self.cards.get_by_id(card_id)
        if card is None or card.user_id != user_id:
            raise NotFoundError("Card not found")

        if benefit.min_card_tier is not None and not self._meets_card_tier(card.tier, benefit.min_card_tier):
            raise ValidationError(f"Requires a {benefit.min_card_tier.value.title()} card")

        points_cost = benefit.points_cost or 0
        reward_transaction = None
        if points_cost > 0:
            if account.points_balance < points_cost:
                raise ConflictError("Insufficient reward points balance")
            account.points_balance -= points_cost
            reward_transaction = self.repository.add_transaction(
                RewardTransaction(
                    reward_account_id=account.id,
                    type=RewardTransactionType.SPEND,
                    points=-points_cost,
                    description=f"Redeemed: {benefit.name}",
                )
            )

        self.repository.add_redemption(
            BenefitRedemption(
                reward_account_id=account.id,
                benefit_id=benefit.id,
                reward_transaction_id=reward_transaction.id if reward_transaction is not None else None,
                card_id=card.id,
                redemption_code=self._generate_redemption_code(),
                points_spent=points_cost,
            )
        )
        self.db.flush()
        return self.get_account(user_id)

    def _best_owned_card_tier(self, user_id: uuid.UUID) -> CardTier | None:
        best: CardTier | None = None
        for card in self.cards.list_for_user(user_id):
            if card.tier is None:
                continue
            if best is None or CARD_TIER_RANK[card.tier] > CARD_TIER_RANK[best]:
                best = card.tier
        return best

    @staticmethod
    def _meets_card_tier(owned: CardTier | None, required: CardTier) -> bool:
        if owned is None:
            return False
        return CARD_TIER_RANK[owned] >= CARD_TIER_RANK[required]

    @staticmethod
    def _generate_redemption_code() -> str:
        return f"RWD-{secrets.token_hex(4).upper()}"

    def _account_to_public(self, account: RewardAccount) -> RewardAccountPublic:
        transactions = self.repository.list_transactions(account.id)
        redemptions = self.repository.list_redemptions(account.id)

        return RewardAccountPublic(
            points_balance=account.points_balance,
            lifetime_points_earned=account.lifetime_points_earned,
            transactions=[self._transaction_to_public(tx) for tx in transactions],
            redemptions=[self._redemption_to_public(r) for r in redemptions],
        )

    def _transaction_to_public(self, tx: RewardTransaction) -> RewardTransactionPublic:
        return RewardTransactionPublic(
            id=tx.id, type=tx.type, points=tx.points, description=tx.description, created_at=tx.created_at
        )

    def _redemption_to_public(self, redemption: BenefitRedemption) -> BenefitRedemptionPublic:
        benefit = None
        try:
            benefit = redemption.benefit
        except DetachedInstanceError:
            benefit = None
        if benefit is None:
            benefit = self.repository.get_benefit(redemption.benefit_id)
        return BenefitRedemptionPublic(
            id=redemption.id,
            benefit_id=redemption.benefit_id,
            benefit_name=benefit.name if benefit is not None else "Unknown benefit",
            card_id=redemption.card_id,
            redemption_code=redemption.redemption_code,
            points_spent=redemption.points_spent,
            redeemed_at=redemption.redeemed_at,
        )
