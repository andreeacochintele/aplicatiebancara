"""Data-access layer for BusinessProfile and BusinessDocument."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import BusinessDocument, BusinessProfile
from app.supabase import is_supabase_session


class BusinessProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, user_id: uuid.UUID) -> list[BusinessProfile]:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_many(
                    BusinessProfile, {"user_id": f"eq.{user_id}", "order": "created_at.asc"}
                )
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc):
                    return []
                raise
        return list(
            self.db.scalars(
                select(BusinessProfile).where(BusinessProfile.user_id == user_id).order_by(BusinessProfile.created_at)
            )
        )

    def list_all(self) -> list[BusinessProfile]:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_many(BusinessProfile, {"order": "created_at.desc"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc):
                    return []
                raise
        return list(self.db.scalars(select(BusinessProfile).order_by(BusinessProfile.created_at.desc())))

    def get_by_id(self, profile_id: uuid.UUID) -> BusinessProfile | None:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_one(BusinessProfile, {"id": f"eq.{profile_id}"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc):
                    return None
                raise
        return self.db.get(BusinessProfile, profile_id)

    def add(self, profile: BusinessProfile) -> BusinessProfile:
        if is_supabase_session(self.db):
            return self.db.add(profile)
        self.db.add(profile)
        self.db.flush()
        return profile

    def _is_missing_supabase_table(self, exc: RuntimeError) -> bool:
        message = str(exc)
        return "PGRST205" in message and BusinessProfile.__tablename__ in message


class BusinessDocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_profile(self, business_profile_id: uuid.UUID) -> list[BusinessDocument]:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_many(
                    BusinessDocument,
                    {"business_profile_id": f"eq.{business_profile_id}", "order": "uploaded_at.asc"},
                )
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc):
                    return []
                raise
        return list(
            self.db.scalars(
                select(BusinessDocument)
                .where(BusinessDocument.business_profile_id == business_profile_id)
                .order_by(BusinessDocument.uploaded_at)
            )
        )

    def list_all(self) -> list[BusinessDocument]:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_many(BusinessDocument, {"order": "uploaded_at.desc"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc):
                    return []
                raise
        return list(self.db.scalars(select(BusinessDocument).order_by(BusinessDocument.uploaded_at.desc())))

    def get_by_id(self, document_id: uuid.UUID) -> BusinessDocument | None:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_one(BusinessDocument, {"id": f"eq.{document_id}"})
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc):
                    return None
                raise
        return self.db.get(BusinessDocument, document_id)

    def add(self, document: BusinessDocument) -> BusinessDocument:
        if is_supabase_session(self.db):
            return self.db.add(document)
        self.db.add(document)
        self.db.flush()
        return document

    def _is_missing_supabase_table(self, exc: RuntimeError) -> bool:
        message = str(exc)
        return "PGRST205" in message and BusinessDocument.__tablename__ in message
