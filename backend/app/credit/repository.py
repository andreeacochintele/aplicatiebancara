"""Data-access layer for credit profiles and score history."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.credit.models import CreditApplication, CreditProfile, CreditScoreHistory, Loan, LoanInstallment
from app.supabase import is_supabase_session


class CreditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_profile_by_user(self, user_id: uuid.UUID) -> CreditProfile | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(CreditProfile, {"user_id": f"eq.{user_id}"})
        return self.db.scalar(select(CreditProfile).where(CreditProfile.user_id == user_id))

    def add_profile(self, profile: CreditProfile) -> CreditProfile:
        if is_supabase_session(self.db):
            return self.db.add(profile)
        self.db.add(profile)
        self.db.flush()
        return profile

    def add_history(self, history: CreditScoreHistory) -> CreditScoreHistory:
        if is_supabase_session(self.db):
            return self.db.add(history)
        self.db.add(history)
        self.db.flush()
        return history

    def latest_history(self, profile_id: uuid.UUID) -> CreditScoreHistory | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                CreditScoreHistory,
                {
                    "credit_profile_id": f"eq.{profile_id}",
                    "order": "created_at.desc",
                },
            )
        stmt = (
            select(CreditScoreHistory)
            .where(CreditScoreHistory.credit_profile_id == profile_id)
            .order_by(CreditScoreHistory.created_at.desc())
        )
        return self.db.scalar(stmt)

    def add_application(self, application: CreditApplication) -> CreditApplication:
        if is_supabase_session(self.db):
            return self.db.add(application)
        self.db.add(application)
        self.db.flush()
        return application

    def get_application_by_id(self, application_id: uuid.UUID) -> CreditApplication | None:
        if is_supabase_session(self.db):
            return self.db.get(CreditApplication, application_id)
        return self.db.get(CreditApplication, application_id)

    def list_applications_for_user(self, user_id: uuid.UUID) -> list[CreditApplication]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                CreditApplication,
                {"user_id": f"eq.{user_id}", "order": "created_at.desc"},
            )
        stmt = (
            select(CreditApplication)
            .where(CreditApplication.user_id == user_id)
            .order_by(CreditApplication.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def list_applications(self) -> list[CreditApplication]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(CreditApplication, {"order": "created_at.desc"})
        stmt = select(CreditApplication).order_by(CreditApplication.created_at.desc())
        return list(self.db.scalars(stmt))

    def add_loan(self, loan: Loan) -> Loan:
        if is_supabase_session(self.db):
            return self.db.add(loan)
        self.db.add(loan)
        self.db.flush()
        return loan

    def add_installments(self, installments: list[LoanInstallment]) -> list[LoanInstallment]:
        if is_supabase_session(self.db):
            return [self.db.add(installment) for installment in installments]
        self.db.add_all(installments)
        self.db.flush()
        return installments

    def get_loan_by_id(self, loan_id: uuid.UUID) -> Loan | None:
        if is_supabase_session(self.db):
            return self.db.get(Loan, loan_id)
        return self.db.get(Loan, loan_id)

    def get_loan_by_application(self, application_id: uuid.UUID) -> Loan | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(Loan, {"application_id": f"eq.{application_id}"})
        return self.db.scalar(select(Loan).where(Loan.application_id == application_id))

    def list_loans_for_user(self, user_id: uuid.UUID) -> list[Loan]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(Loan, {"user_id": f"eq.{user_id}", "order": "created_at.desc"})
        stmt = select(Loan).where(Loan.user_id == user_id).order_by(Loan.created_at.desc())
        return list(self.db.scalars(stmt))

    def list_installments_for_loan(self, loan_id: uuid.UUID) -> list[LoanInstallment]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                LoanInstallment,
                {"loan_id": f"eq.{loan_id}", "order": "installment_number.asc"},
            )
        stmt = (
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan_id)
            .order_by(LoanInstallment.installment_number.asc())
        )
        return list(self.db.scalars(stmt))
