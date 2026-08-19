"""Data-access layer for payment beneficiaries."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.payments.models import Beneficiary, PaymentRequest, ScheduledPayment


class BeneficiaryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owned_by_id(self, owner_user_id: uuid.UUID, beneficiary_id: uuid.UUID) -> Beneficiary | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                Beneficiary,
                {"id": f"eq.{beneficiary_id}", "owner_user_id": f"eq.{owner_user_id}"},
            )
        return self.db.scalar(
            select(Beneficiary).where(
                Beneficiary.id == beneficiary_id,
                Beneficiary.owner_user_id == owner_user_id,
            )
        )

    def list_for_owner(self, owner_user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[Beneficiary]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                Beneficiary,
                {
                    "owner_user_id": f"eq.{owner_user_id}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
        stmt = (
            select(Beneficiary)
            .where(Beneficiary.owner_user_id == owner_user_id)
            .order_by(Beneficiary.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def add(self, beneficiary: Beneficiary) -> Beneficiary:
        if is_supabase_session(self.db):
            return self.db.add(beneficiary)
        self.db.add(beneficiary)
        self.db.flush()
        return beneficiary

    def delete(self, beneficiary: Beneficiary) -> None:
        if is_supabase_session(self.db):
            self.db.delete(beneficiary)
            return
        self.db.delete(beneficiary)
        self.db.flush()


class PaymentRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: uuid.UUID) -> PaymentRequest | None:
        if is_supabase_session(self.db):
            return self.db.get(PaymentRequest, request_id)
        return self.db.get(PaymentRequest, request_id)

    def add(self, payment_request: PaymentRequest) -> PaymentRequest:
        if is_supabase_session(self.db):
            return self.db.add(payment_request)
        self.db.add(payment_request)
        self.db.flush()
        return payment_request


class ScheduledPaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owned_by_id(self, owner_user_id: uuid.UUID, scheduled_payment_id: uuid.UUID) -> ScheduledPayment | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                ScheduledPayment,
                {"id": f"eq.{scheduled_payment_id}", "owner_user_id": f"eq.{owner_user_id}"},
            )
        return self.db.scalar(
            select(ScheduledPayment).where(
                ScheduledPayment.id == scheduled_payment_id,
                ScheduledPayment.owner_user_id == owner_user_id,
            )
        )

    def list_for_owner(self, owner_user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[ScheduledPayment]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                ScheduledPayment,
                {
                    "owner_user_id": f"eq.{owner_user_id}",
                    "order": "next_run_on.asc,created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
        stmt = (
            select(ScheduledPayment)
            .where(ScheduledPayment.owner_user_id == owner_user_id)
            .order_by(ScheduledPayment.next_run_on.asc(), ScheduledPayment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def add(self, scheduled_payment: ScheduledPayment) -> ScheduledPayment:
        if is_supabase_session(self.db):
            return self.db.add(scheduled_payment)
        self.db.add(scheduled_payment)
        self.db.flush()
        return scheduled_payment

    def delete(self, scheduled_payment: ScheduledPayment) -> None:
        if is_supabase_session(self.db):
            self.db.delete(scheduled_payment)
            return
        self.db.delete(scheduled_payment)
        self.db.flush()
