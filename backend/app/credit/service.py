"""Credit profile and score business rules."""
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.credit.models import CreditProfile, CreditScoreHistory
from app.credit.repository import CreditRepository
from app.credit.schemas import CreditScorePublic, CreditScoreRecalculateRequest
from app.credit.scoring import calculate_credit_score, credit_band
from app.wallets.repository import WalletRepository


class CreditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CreditRepository(db)
        self.wallets = WalletRepository(db)

    def get_or_create_profile(self, user_id: uuid.UUID) -> CreditProfile:
        profile = self.repository.get_profile_by_user(user_id)
        if profile is not None:
            return profile

        profile = self.repository.add_profile(CreditProfile(user_id=user_id))
        self._persist_score(profile, self._wallet_balance(user_id))
        return profile

    def get_score(self, user_id: uuid.UUID) -> CreditScorePublic:
        profile = self.get_or_create_profile(user_id)
        latest = self.repository.latest_history(profile.id)
        if latest is None:
            latest = self._persist_score(profile, self._wallet_balance(user_id))
        return CreditScorePublic(
            score=profile.current_score,
            band=credit_band(profile.current_score),
            reason_data=latest.reason_data,
            calculated_at=latest.created_at,
        )

    def recalculate_score(self, user_id: uuid.UUID, data: CreditScoreRecalculateRequest) -> CreditScorePublic:
        profile = self.repository.get_profile_by_user(user_id)
        if profile is None:
            profile = self.repository.add_profile(CreditProfile(user_id=user_id))

        if data.income is not None:
            profile.income = data.income
        if data.existing_debt is not None:
            profile.existing_debt = data.existing_debt

        history = self._persist_score(profile, self._wallet_balance(user_id))
        return CreditScorePublic(
            score=profile.current_score,
            band=credit_band(profile.current_score),
            reason_data=history.reason_data,
            calculated_at=history.created_at,
        )

    def _wallet_balance(self, user_id: uuid.UUID) -> Decimal:
        return sum((wallet.available_balance for wallet in self.wallets.list_for_user(user_id)), Decimal("0"))

    def _persist_score(self, profile: CreditProfile, wallet_balance: Decimal) -> CreditScoreHistory:
        score, factors = calculate_credit_score(profile.income, profile.existing_debt, wallet_balance)
        profile.current_score = score
        history = CreditScoreHistory(
            credit_profile_id=profile.id,
            score=score,
            reason_data={
                **factors,
                "wallet_balance": str(wallet_balance),
                "income": str(profile.income),
                "existing_debt": str(profile.existing_debt),
            },
        )
        return self.repository.add_history(history)
