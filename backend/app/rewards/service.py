"""Bank reward points ledger business rules (architecture.md §11).

`earn_points` is also called from app.merchants.service when a mock purchase
is recorded at a merchant — it's the one place a caller other than this
module's own router is allowed to credit points.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.rewards.models import RewardAccount, RewardTransaction, RewardTransactionType
from app.rewards.repository import RewardsRepository
from app.rewards.schemas import RewardAccountPublic, RewardTransactionPublic


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
        transactions = self.repository.list_transactions(account.id)
        return RewardAccountPublic(
            points_balance=account.points_balance,
            transactions=[self._to_public(tx) for tx in transactions],
        )

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

    def _to_public(self, tx: RewardTransaction) -> RewardTransactionPublic:
        return RewardTransactionPublic(
            id=tx.id, type=tx.type, points=tx.points, description=tx.description, created_at=tx.created_at
        )
