"""Credit profile and score business rules."""
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.credit.models import CreditApplication, CreditApplicationStatus, CreditApplicationType, CreditProfile, CreditScoreHistory
from app.credit.repository import CreditRepository
from app.credit.schemas import CreditApplicationCreate, CreditScorePublic, CreditScoreRecalculateRequest
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

    def create_application(self, user_id: uuid.UUID, data: CreditApplicationCreate) -> CreditApplication:
        if data.requested_amount <= 0:
            raise ValidationError("Requested amount must be positive")
        if data.type == CreditApplicationType.PERSONAL_LOAN:
            if data.requested_term_months is None or data.requested_term_months <= 0:
                raise ValidationError("Personal loan applications require a positive term")
        elif data.requested_term_months is not None and data.requested_term_months <= 0:
            raise ValidationError("Requested term must be positive")

        score = self.get_score(user_id)
        application = CreditApplication(
            user_id=user_id,
            type=data.type,
            requested_amount=data.requested_amount,
            requested_term_months=data.requested_term_months,
            credit_score_at_application=score.score,
            status=CreditApplicationStatus.PENDING,
        )
        return self.repository.add_application(application)

    def list_applications(self, user_id: uuid.UUID) -> list[CreditApplication]:
        return self.repository.list_applications_for_user(user_id)

    def get_application_for_user(self, user_id: uuid.UUID, application_id: uuid.UUID) -> CreditApplication:
        application = self.repository.get_application_by_id(application_id)
        if application is None or application.user_id != user_id:
            raise NotFoundError("Credit application not found")
        return application

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
