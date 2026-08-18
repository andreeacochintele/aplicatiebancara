"""Data-access layer for RewardAccount and RewardTransaction."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.rewards.models import RewardAccount, RewardTransaction


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
