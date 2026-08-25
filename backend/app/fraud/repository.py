"""Data-access layer for FraudCase and FraudFlag, plus the read-only device
lookups the fraud engine needs from app.auth (session/device tracking)."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import SessionStatus, UserDevice, UserSession
from app.fraud.models import FraudCase, FraudCaseStatus, FraudFlag
from app.supabase import is_supabase_session


class FraudRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, case: FraudCase) -> FraudCase:
        if is_supabase_session(self.db):
            return self.db.add(case)
        self.db.add(case)
        self.db.flush()
        return case

    def add_flag(self, flag: FraudFlag) -> FraudFlag:
        if is_supabase_session(self.db):
            return self.db.add(flag)
        self.db.add(flag)
        self.db.flush()
        return flag

    def get_by_id(self, case_id: uuid.UUID) -> FraudCase | None:
        if is_supabase_session(self.db):
            return self.db.get(FraudCase, case_id)
        return self.db.get(FraudCase, case_id)

    def list_pending(self) -> list[FraudCase]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                FraudCase, {"status": f"eq.{FraudCaseStatus.PENDING_REVIEW.value}", "order": "created_at.asc"}
            )
        stmt = (
            select(FraudCase)
            .where(FraudCase.status == FraudCaseStatus.PENDING_REVIEW)
            .order_by(FraudCase.created_at.asc())
        )
        return list(self.db.scalars(stmt))

    def list_for_user(self, user_id: uuid.UUID) -> list[FraudCase]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(FraudCase, {"user_id": f"eq.{user_id}", "order": "created_at.desc"})
        stmt = select(FraudCase).where(FraudCase.user_id == user_id).order_by(FraudCase.created_at.desc())
        return list(self.db.scalars(stmt))

    def list_flags_for_case(self, case_id: uuid.UUID) -> list[FraudFlag]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(FraudFlag, {"fraud_case_id": f"eq.{case_id}"})
        stmt = select(FraudFlag).where(FraudFlag.fraud_case_id == case_id)
        return list(self.db.scalars(stmt))

    def get_latest_device_for_user(self, user_id: uuid.UUID) -> UserDevice | None:
        """The device behind the user's most recently active session — used as
        a proxy for "which device is paying" since create_card_payment isn't
        passed any device/session context of its own."""
        if is_supabase_session(self.db):
            sessions = self.db.fetch_many(
                UserSession,
                {
                    "user_id": f"eq.{user_id}",
                    "status": f"eq.{SessionStatus.ACTIVE.value}",
                    "order": "last_activity_at.desc",
                },
            )
            session = next((s for s in sessions if s.device_id is not None), None)
            return self.db.get(UserDevice, session.device_id) if session is not None else None

        stmt = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.status == SessionStatus.ACTIVE,
                UserSession.device_id.is_not(None),
            )
            .order_by(UserSession.last_activity_at.desc())
        )
        session = self.db.scalars(stmt).first()
        return self.db.get(UserDevice, session.device_id) if session is not None else None

    def list_devices_for_user(self, user_id: uuid.UUID) -> list[UserDevice]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(UserDevice, {"user_id": f"eq.{user_id}"})
        stmt = select(UserDevice).where(UserDevice.user_id == user_id)
        return list(self.db.scalars(stmt))
