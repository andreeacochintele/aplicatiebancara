"""Data-access layer for the rewards ledger, tiers and the benefits catalog."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.rewards.models import (
    BenefitRedemption,
    BenefitStatus,
    RewardAccount,
    RewardBenefit,
    RewardTransaction,
)
from app.supabase import is_supabase_session


class RewardsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_account_for_user(self, user_id: uuid.UUID) -> RewardAccount | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(RewardAccount, {"user_id": f"eq.{user_id}"})
        stmt = select(RewardAccount).where(RewardAccount.user_id == user_id)
        return self.db.scalars(stmt).first()

    def add_account(self, account: RewardAccount) -> RewardAccount:
        if is_supabase_session(self.db):
            return self.db.add(account)
        self.db.add(account)
        self.db.flush()
        return account

    def add_transaction(self, transaction: RewardTransaction) -> RewardTransaction:
        if is_supabase_session(self.db):
            return self.db.add(transaction)
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def list_transactions(self, reward_account_id: uuid.UUID) -> list[RewardTransaction]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                RewardTransaction,
                {"reward_account_id": f"eq.{reward_account_id}", "order": "created_at.desc,points.asc"},
            )
        stmt = (
            select(RewardTransaction)
            .where(RewardTransaction.reward_account_id == reward_account_id)
            .order_by(RewardTransaction.created_at.desc(), RewardTransaction.points.asc())
        )
        return list(self.db.scalars(stmt))

    def has_transaction_for_source(self, source_transaction_id: uuid.UUID) -> bool:
        stmt = select(RewardTransaction.id).where(RewardTransaction.source_transaction_id == source_transaction_id)
        return self.db.scalar(stmt) is not None

    def list_active_benefits(self) -> list[RewardBenefit]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(RewardBenefit, {"status": f"eq.{BenefitStatus.ACTIVE.value}", "order": "name.asc"})
        stmt = select(RewardBenefit).where(RewardBenefit.status == BenefitStatus.ACTIVE)
        return list(self.db.scalars(stmt))

    def get_benefit(self, benefit_id: uuid.UUID) -> RewardBenefit | None:
        if is_supabase_session(self.db):
            return self.db.get(RewardBenefit, benefit_id)
        return self.db.get(RewardBenefit, benefit_id)

    def add_redemption(self, redemption: BenefitRedemption) -> BenefitRedemption:
        if is_supabase_session(self.db):
            return self.db.add(redemption)
        self.db.add(redemption)
        self.db.flush()
        return redemption

    def list_redemptions(self, reward_account_id: uuid.UUID) -> list[BenefitRedemption]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                BenefitRedemption,
                {"reward_account_id": f"eq.{reward_account_id}", "order": "redeemed_at.desc"},
            )
        stmt = (
            select(BenefitRedemption)
            .where(BenefitRedemption.reward_account_id == reward_account_id)
            .order_by(BenefitRedemption.redeemed_at.desc())
        )
        return list(self.db.scalars(stmt))
