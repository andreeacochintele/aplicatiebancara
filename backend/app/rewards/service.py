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
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import DetachedInstanceError

from app.cards.models import CardTier
from app.cards.repository import CardRepository
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.database import utcnow
from app.rewards.models import (
    BenefitRedemption,
    BenefitStatus,
    RedemptionStatus,
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

# How long a redeemed voucher stays presentable at the partner before it
# expires — a fixed demo rule, not configurable per benefit yet.
REDEMPTION_VALIDITY = timedelta(days=30)


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) drops tzinfo on round-trip even for
    DateTime(timezone=True) columns; Postgres preserves it. Normalize so
    comparisons against `datetime.now(timezone.utc)` work on both — same
    pattern as app/fx/service.py and app/payments/service.py."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class RewardsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = RewardsRepository(db)
        self.cards = CardRepository(db)

    def get_or_create_account(self, user_id: uuid.UUID) -> RewardAccount:
        account = self.repository.get_account_for_user(user_id)
        if account is None:
            account = self.repository.add_account(
                RewardAccount(user_id=user_id, referral_code=self._generate_referral_code())
            )
        elif account.referral_code is None:
            # Backfill for accounts created before referral codes existed.
            account.referral_code = self._generate_referral_code()
            self.db.flush()
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
        proof_code: str | None = None,
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
                proof_code=proof_code,
            )
        )
        self.db.flush()
        return account

    def has_earned_for_transaction(self, source_transaction_id: uuid.UUID) -> bool:
        return self.repository.has_transaction_for_source(source_transaction_id)

    def get_synced_transaction_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """All source_transaction_ids already earning-recorded for this user,
        fetched in one call — used by MerchantService.sync_purchases_from_transactions
        to filter its transaction list in memory instead of doing one
        has_earned_for_transaction REST round-trip per transaction, which is
        what made sync scale O(transaction count) network calls."""
        account = self.get_or_create_account(user_id)
        return {
            tx.source_transaction_id
            for tx in self.repository.list_transactions(account.id)
            if tx.source_transaction_id is not None
        }

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

        # Eligibility is about which cards the user owns overall, not which
        # one happens to be selected in this redemption's "pay with" dropdown
        # (that field is receipt/audit only — see BenefitRedemption.card_id).
        # A Platinum-card owner can redeem a Gold-gated benefit even while
        # this dropdown has a Regular card selected; list_benefits() already
        # gates the same way via _best_owned_card_tier.
        if benefit.min_card_tier is not None and not self._meets_card_tier(
            self._best_owned_card_tier(user_id), benefit.min_card_tier
        ):
            raise ValidationError(f"Requires a {benefit.min_card_tier.value.title()} card")

        points_cost = benefit.points_cost or 0
        if points_cost > 0 and account.points_balance < points_cost:
            raise ConflictError("Insufficient reward points balance")

        # Create the redemption row before touching the points balance: under
        # SupabaseRestSession there's no real transaction to roll back, so if
        # this insert fails (e.g. the shared DB's schema is behind), nothing
        # else has been mutated yet — no dangling SPEND transaction with a
        # balance that was never actually decremented.
        now = utcnow()
        redemption = self.repository.add_redemption(
            BenefitRedemption(
                reward_account_id=account.id,
                benefit_id=benefit.id,
                reward_transaction_id=None,
                card_id=card.id,
                redemption_code=self._generate_redemption_code(),
                points_spent=points_cost,
                redeemed_at=now,
                expires_at=now + REDEMPTION_VALIDITY,
            )
        )

        if points_cost > 0:
            account.points_balance -= points_cost
            reward_transaction = self.repository.add_transaction(
                RewardTransaction(
                    reward_account_id=account.id,
                    type=RewardTransactionType.SPEND,
                    points=-points_cost,
                    description=f"Redeemed: {benefit.name}",
                )
            )
            redemption.reward_transaction_id = reward_transaction.id

        self.db.flush()
        return self.get_account(user_id)

    def mark_redemption_used(self, user_id: uuid.UUID, redemption_id: uuid.UUID) -> RewardAccountPublic:
        account = self.get_or_create_account(user_id)
        redemption = self.repository.get_redemption(redemption_id)
        if redemption is None or redemption.reward_account_id != account.id:
            raise NotFoundError("Voucher not found")
        if redemption.used_at is not None:
            raise ValidationError("Voucher already used")
        if redemption.expires_at is not None and utcnow() > _as_aware_utc(redemption.expires_at):
            raise ValidationError("Voucher expired")

        redemption.used_at = utcnow()
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

    @staticmethod
    def _generate_referral_code() -> str:
        return f"AURORA-{secrets.token_hex(4).upper()}"

    def _account_to_public(self, account: RewardAccount) -> RewardAccountPublic:
        transactions = self.repository.list_transactions(account.id)
        redemptions = self.repository.list_redemptions(account.id)

        return RewardAccountPublic(
            points_balance=account.points_balance,
            lifetime_points_earned=account.lifetime_points_earned,
            referral_code=account.referral_code,
            transactions=[self._transaction_to_public(tx) for tx in transactions],
            redemptions=[self._redemption_to_public(r) for r in redemptions],
        )

    def _transaction_to_public(self, tx: RewardTransaction) -> RewardTransactionPublic:
        return RewardTransactionPublic(
            id=tx.id,
            type=tx.type,
            points=tx.points,
            description=tx.description,
            proof_code=tx.proof_code,
            created_at=tx.created_at,
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
            expires_at=redemption.expires_at,
            used_at=redemption.used_at,
            status=self._redemption_status(redemption),
        )

    @staticmethod
    def _redemption_status(redemption: BenefitRedemption) -> RedemptionStatus:
        if redemption.used_at is not None:
            return RedemptionStatus.USED
        if redemption.expires_at is not None and utcnow() > _as_aware_utc(redemption.expires_at):
            return RedemptionStatus.EXPIRED
        return RedemptionStatus.VALID
