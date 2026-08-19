"""Data-access layer for the rewards ledger, tiers and the benefits catalog."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.rewards.models import (
    BenefitRedemption,
    BenefitStatus,
    RewardAccount,
    RewardBenefit,
    RewardTier,
    RewardTransaction,
)


class RewardsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_account_for_user(self, user_id: uuid.UUID) -> RewardAccount | None:
        stmt = select(RewardAccount).where(RewardAccount.user_id == user_id)
        return self.db.scalars(stmt).first()

    def add_account(self, account: RewardAccount) -> RewardAccount:
        self.db.add(account)
        self.db.flush()
        return account

    def add_transaction(self, transaction: RewardTransaction) -> RewardTransaction:
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def list_transactions(self, reward_account_id: uuid.UUID) -> list[RewardTransaction]:
        stmt = (
            select(RewardTransaction)
            .where(RewardTransaction.reward_account_id == reward_account_id)
            .order_by(RewardTransaction.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def has_transaction_for_source(self, source_transaction_id: uuid.UUID) -> bool:
        stmt = select(RewardTransaction.id).where(RewardTransaction.source_transaction_id == source_transaction_id)
        return self.db.scalar(stmt) is not None

    def list_tiers(self) -> list[RewardTier]:
        stmt = select(RewardTier).order_by(RewardTier.sort_order)
        return list(self.db.scalars(stmt))

    def list_active_benefits(self) -> list[RewardBenefit]:
        stmt = select(RewardBenefit).where(RewardBenefit.status == BenefitStatus.ACTIVE)
        return list(self.db.scalars(stmt))

    def get_benefit(self, benefit_id: uuid.UUID) -> RewardBenefit | None:
        return self.db.get(RewardBenefit, benefit_id)

    def add_redemption(self, redemption: BenefitRedemption) -> BenefitRedemption:
        self.db.add(redemption)
        self.db.flush()
        return redemption

    def list_redemptions(self, reward_account_id: uuid.UUID) -> list[BenefitRedemption]:
        stmt = (
            select(BenefitRedemption)
            .where(BenefitRedemption.reward_account_id == reward_account_id)
            .order_by(BenefitRedemption.redeemed_at.desc())
        )
        return list(self.db.scalars(stmt))
