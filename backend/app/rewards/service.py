"""Bank reward points ledger, tiers and benefits catalog (architecture.md §11).

`earn_points` is also called from app.merchants.service when a mock purchase
is recorded at a merchant — it's the one place a caller other than this
module's own router is allowed to credit points.

Tiers are Revolut-style: `RewardAccount.lifetime_points_earned` only ever
grows (unlike `points_balance`, which drops on redeem), and the account's
tier is derived from it on read rather than stored, so it's always
consistent with the ledger. Tier perks are descriptive only for now — e.g.
a "10% bonus points" perk isn't wired into MerchantService's point math yet,
the same kind of informational simplification cashback offers already use.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.rewards.models import (
    BenefitRedemption,
    BenefitStatus,
    RewardAccount,
    RewardBenefit,
    RewardTier,
    RewardTransaction,
    RewardTransactionType,
)
from app.rewards.repository import RewardsRepository
from app.rewards.schemas import (
    BenefitRedemptionPublic,
    RewardAccountPublic,
    RewardBenefitPublic,
    RewardTierPublic,
    RewardTransactionPublic,
)


class RewardsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = RewardsRepository(db)

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
        tiers_by_id = {tier.id: tier for tier in self.repository.list_tiers()}
        current_tier = self._tier_for(account.lifetime_points_earned)

        result = []
        for benefit in self.repository.list_active_benefits():
            min_tier = tiers_by_id.get(benefit.min_tier_id) if benefit.min_tier_id else None
            locked_reason = None
            if min_tier is not None and min_tier.sort_order > current_tier.sort_order:
                locked_reason = f"Requires {min_tier.name} tier"
            elif benefit.points_cost is not None and account.points_balance < benefit.points_cost:
                locked_reason = "Not enough points"

            result.append(
                RewardBenefitPublic(
                    id=benefit.id,
                    name=benefit.name,
                    category=benefit.category,
                    description=benefit.description,
                    points_cost=benefit.points_cost,
                    min_tier=self._tier_to_public(min_tier) if min_tier is not None else None,
                    partner_name=benefit.partner_name,
                    can_redeem=locked_reason is None,
                    reason_if_locked=locked_reason,
                )
            )
        return result

    def redeem_benefit(self, user_id: uuid.UUID, benefit_id: uuid.UUID) -> RewardAccountPublic:
        account = self.get_or_create_account(user_id)
        benefit = self.repository.get_benefit(benefit_id)
        if benefit is None or benefit.status != BenefitStatus.ACTIVE:
            raise NotFoundError("Benefit not found")

        tiers_by_id = {tier.id: tier for tier in self.repository.list_tiers()}
        current_tier = self._tier_for(account.lifetime_points_earned)
        min_tier = tiers_by_id.get(benefit.min_tier_id) if benefit.min_tier_id else None
        if min_tier is not None and min_tier.sort_order > current_tier.sort_order:
            raise ValidationError(f"Requires {min_tier.name} tier")

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
                points_spent=points_cost,
            )
        )
        self.db.flush()
        return self.get_account(user_id)

    def _tier_for(self, lifetime_points: int) -> RewardTier:
        tiers = self.repository.list_tiers()
        eligible = [tier for tier in tiers if tier.min_lifetime_points <= lifetime_points]
        return eligible[-1] if eligible else tiers[0]

    def _next_tier(self, current: RewardTier) -> RewardTier | None:
        higher = [tier for tier in self.repository.list_tiers() if tier.sort_order > current.sort_order]
        return higher[0] if higher else None

    def _account_to_public(self, account: RewardAccount) -> RewardAccountPublic:
        tier = self._tier_for(account.lifetime_points_earned)
        next_tier = self._next_tier(tier)
        transactions = self.repository.list_transactions(account.id)
        redemptions = self.repository.list_redemptions(account.id)

        return RewardAccountPublic(
            points_balance=account.points_balance,
            lifetime_points_earned=account.lifetime_points_earned,
            tier=self._tier_to_public(tier),
            next_tier=self._tier_to_public(next_tier) if next_tier is not None else None,
            points_to_next_tier=(
                next_tier.min_lifetime_points - account.lifetime_points_earned if next_tier is not None else None
            ),
            transactions=[self._transaction_to_public(tx) for tx in transactions],
            redemptions=[self._redemption_to_public(r) for r in redemptions],
        )

    def _tier_to_public(self, tier: RewardTier) -> RewardTierPublic:
        return RewardTierPublic(
            id=tier.id, name=tier.name, min_lifetime_points=tier.min_lifetime_points, perks=tier.perks.split("|")
        )

    def _transaction_to_public(self, tx: RewardTransaction) -> RewardTransactionPublic:
        return RewardTransactionPublic(
            id=tx.id, type=tx.type, points=tx.points, description=tx.description, created_at=tx.created_at
        )

    def _redemption_to_public(self, redemption: BenefitRedemption) -> BenefitRedemptionPublic:
        return BenefitRedemptionPublic(
            id=redemption.id,
            benefit_id=redemption.benefit_id,
            benefit_name=redemption.benefit.name,
            points_spent=redemption.points_spent,
            redeemed_at=redemption.redeemed_at,
        )
