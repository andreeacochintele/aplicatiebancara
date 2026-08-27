"""Data-access layer for credit profiles and score history."""
import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.credit.models import (
    CreditApplication,
    CreditDocument,
    CreditDocumentPurpose,
    CreditDocumentStatus,
    CreditProfile,
    CreditScoreHistory,
    Loan,
    LoanInstallment,
    LoanPayment,
)
from app.supabase import is_supabase_session

_MEMORY_CREDIT_DOCUMENTS: dict[uuid.UUID, CreditDocument] = {}
_MEMORY_CREDIT_DOCUMENT_CONTENTS: dict[uuid.UUID, str] = {}
_MEMORY_CREDIT_DOCUMENT_OVERLAYS: dict[uuid.UUID, CreditDocument] = {}
_DOCUMENT_STORE_PATH = Path(
    os.environ.get("CREDIT_DOCUMENT_STORE_PATH", str(Path(__file__).resolve().parents[2] / ".credit_documents.json"))
)


class CreditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _normalize_application(self, application: CreditApplication | None) -> CreditApplication | None:
        if application is not None and application.currency is None:
            application.currency = "RON"
        return application

    def _normalize_loan(self, loan: Loan | None) -> Loan | None:
        if loan is None:
            return None
        if loan.currency is None:
            loan.currency = "RON"
        fallback_date = self._loan_fallback_date(loan)
        if loan.start_date is None:
            loan.start_date = fallback_date
        if loan.next_payment_date is None:
            loan.next_payment_date = fallback_date
        if loan.maturity_date is None:
            loan.maturity_date = fallback_date
        return loan

    def _loan_fallback_date(self, loan: Loan) -> date:
        created_at = loan.created_at
        if isinstance(created_at, datetime):
            return created_at.date()
        if isinstance(created_at, date):
            return created_at
        return date.today()

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

    def add_document(self, document: CreditDocument) -> CreditDocument:
        if is_supabase_session(self.db):
            if document.id is None:
                document.id = uuid.uuid4()
            _MEMORY_CREDIT_DOCUMENT_OVERLAYS[document.id] = document
            if document.content_base64:
                _MEMORY_CREDIT_DOCUMENT_CONTENTS[document.id] = document.content_base64
            try:
                if not self.ensure_document_storage_available():
                    return self._add_local_document(document)
                stored = self.db.add(document)
                return self._restore_document_overlay(stored)
            except RuntimeError as exc:
                if self._is_supabase_document_storage_error(exc):
                    return self._add_local_document(document)
                raise
        self.db.add(document)
        self.db.flush()
        return document

    def ensure_document_storage_available(self) -> bool:
        if not is_supabase_session(self.db):
            return True
        try:
            self.db.request(
                "GET",
                CreditDocument.__tablename__,
                params={"select": "id,application_id,content_base64", "limit": "1"},
            )
            return True
        except RuntimeError as exc:
            if self._is_supabase_document_storage_error(exc):
                return False
            raise

    def persist_document(self, document: CreditDocument) -> None:
        if is_supabase_session(self.db) and self._get_local_document(document.id) is not None:
            self._add_local_document(document)

    def get_document_by_id(self, document_id: uuid.UUID) -> CreditDocument | None:
        if is_supabase_session(self.db):
            try:
                document = self.db.get(CreditDocument, document_id)
                return self._restore_document_overlay(document) or self._get_local_document(document_id)
            except RuntimeError as exc:
                if self._is_supabase_document_storage_error(exc):
                    return self._get_local_document(document_id)
                raise
        return self.db.get(CreditDocument, document_id)

    def list_documents_for_user(self, user_id: uuid.UUID) -> list[CreditDocument]:
        if is_supabase_session(self.db):
            local_documents = [document for document in self._list_local_documents() if document.user_id == user_id]
            try:
                documents = [
                    document
                    for document in (
                        self._restore_document_overlay(document)
                        for document in self.db.fetch_many(CreditDocument, {"user_id": f"eq.{user_id}", "order": "uploaded_at.desc"})
                    )
                    if document is not None
                ]
            except RuntimeError as exc:
                if self._is_supabase_document_storage_error(exc):
                    documents = []
                else:
                    raise
            return self._merge_documents(documents, local_documents)
        stmt = select(CreditDocument).where(CreditDocument.user_id == user_id).order_by(CreditDocument.uploaded_at.desc())
        return list(self.db.scalars(stmt))

    def list_documents(self) -> list[CreditDocument]:
        if is_supabase_session(self.db):
            local_documents = self._list_local_documents()
            try:
                documents = [
                    document
                    for document in (
                        self._restore_document_overlay(document)
                        for document in self.db.fetch_many(CreditDocument, {"order": "uploaded_at.desc"})
                    )
                    if document is not None
                ]
            except RuntimeError as exc:
                if self._is_supabase_document_storage_error(exc):
                    documents = []
                else:
                    raise
            return self._merge_documents(documents, local_documents)
        stmt = select(CreditDocument).order_by(CreditDocument.uploaded_at.desc())
        return list(self.db.scalars(stmt))

    def get_application_by_id(self, application_id: uuid.UUID) -> CreditApplication | None:
        if is_supabase_session(self.db):
            return self._normalize_application(self.db.get(CreditApplication, application_id))
        return self.db.get(CreditApplication, application_id)

    def list_applications_for_user(self, user_id: uuid.UUID) -> list[CreditApplication]:
        if is_supabase_session(self.db):
            applications = self.db.fetch_many(
                CreditApplication,
                {"user_id": f"eq.{user_id}", "order": "created_at.desc"},
            )
            return [self._normalize_application(application) for application in applications if application is not None]
        stmt = (
            select(CreditApplication)
            .where(CreditApplication.user_id == user_id)
            .order_by(CreditApplication.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def list_applications(self) -> list[CreditApplication]:
        if is_supabase_session(self.db):
            applications = self.db.fetch_many(CreditApplication, {"order": "created_at.desc"})
            return [self._normalize_application(application) for application in applications if application is not None]
        stmt = select(CreditApplication).order_by(CreditApplication.created_at.desc())
        return list(self.db.scalars(stmt))

    def _restore_document_overlay(self, document: CreditDocument | None) -> CreditDocument | None:
        if document is None:
            return None
        overlay = _MEMORY_CREDIT_DOCUMENT_OVERLAYS.get(document.id)
        if overlay is None:
            if document.content_base64 is None:
                document.content_base64 = _MEMORY_CREDIT_DOCUMENT_CONTENTS.get(document.id)
            return document
        if document.application_id is None:
            document.application_id = overlay.application_id
        if document.content_base64 is None:
            document.content_base64 = _MEMORY_CREDIT_DOCUMENT_CONTENTS.get(document.id) or overlay.content_base64
        return document

    def _add_local_document(self, document: CreditDocument) -> CreditDocument:
        if document.uploaded_at is None:
            document.uploaded_at = datetime.now(timezone.utc)
        if document.status is None:
            document.status = CreditDocumentStatus.UPLOADED
        _MEMORY_CREDIT_DOCUMENTS[document.id] = document
        documents = {str(item.id): item for item in self._list_local_documents()}
        documents[str(document.id)] = document
        self._save_local_documents(list(documents.values()))
        return document

    def _get_local_document(self, document_id: uuid.UUID) -> CreditDocument | None:
        return _MEMORY_CREDIT_DOCUMENTS.get(document_id) or next(
            (document for document in self._list_local_documents() if document.id == document_id),
            None,
        )

    def _list_local_documents(self) -> list[CreditDocument]:
        if not _DOCUMENT_STORE_PATH.exists():
            return sorted(_MEMORY_CREDIT_DOCUMENTS.values(), key=lambda document: document.uploaded_at, reverse=True)
        try:
            payload = json.loads(_DOCUMENT_STORE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = []
        documents = [self._document_from_payload(item) for item in payload if isinstance(item, dict)]
        for document in documents:
            _MEMORY_CREDIT_DOCUMENTS[document.id] = document
            if document.content_base64:
                _MEMORY_CREDIT_DOCUMENT_CONTENTS[document.id] = document.content_base64
        return sorted(documents, key=lambda document: document.uploaded_at, reverse=True)

    def _save_local_documents(self, documents: list[CreditDocument]) -> None:
        _DOCUMENT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DOCUMENT_STORE_PATH.write_text(
            json.dumps([self._document_payload(document) for document in documents], indent=2),
            encoding="utf-8",
        )

    def _merge_documents(
        self,
        primary_documents: list[CreditDocument],
        fallback_documents: list[CreditDocument],
    ) -> list[CreditDocument]:
        merged: dict[uuid.UUID, CreditDocument] = {}
        for document in [*fallback_documents, *primary_documents]:
            merged[document.id] = document
        return sorted(merged.values(), key=lambda document: document.uploaded_at, reverse=True)

    def _document_payload(self, document: CreditDocument) -> dict[str, object | None]:
        return {
            "id": str(document.id),
            "user_id": str(document.user_id),
            "application_id": str(document.application_id) if document.application_id else None,
            "purpose": document.purpose.value,
            "document_type": document.document_type,
            "file_name": document.file_name,
            "content_type": document.content_type,
            "file_size": document.file_size,
            "content_base64": document.content_base64,
            "status": document.status.value,
            "evaluation_score": document.evaluation_score,
            "review_note": document.review_note,
            "uploaded_at": document.uploaded_at.isoformat(),
            "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
            "reviewed_by_admin_id": str(document.reviewed_by_admin_id) if document.reviewed_by_admin_id else None,
        }

    def _document_from_payload(self, payload: dict[str, object]) -> CreditDocument:
        return CreditDocument(
            id=uuid.UUID(str(payload["id"])),
            user_id=uuid.UUID(str(payload["user_id"])),
            application_id=uuid.UUID(str(payload["application_id"])) if payload.get("application_id") else None,
            purpose=CreditDocumentPurpose(str(payload["purpose"])),
            document_type=str(payload["document_type"]),
            file_name=str(payload["file_name"]),
            content_type=str(payload["content_type"]) if payload.get("content_type") else None,
            file_size=int(payload.get("file_size") or 0),
            content_base64=str(payload["content_base64"]) if payload.get("content_base64") else None,
            status=CreditDocumentStatus(str(payload["status"])),
            evaluation_score=int(payload["evaluation_score"]) if payload.get("evaluation_score") is not None else None,
            review_note=str(payload["review_note"]) if payload.get("review_note") else None,
            uploaded_at=datetime.fromisoformat(str(payload["uploaded_at"])),
            reviewed_at=datetime.fromisoformat(str(payload["reviewed_at"])) if payload.get("reviewed_at") else None,
            reviewed_by_admin_id=uuid.UUID(str(payload["reviewed_by_admin_id"])) if payload.get("reviewed_by_admin_id") else None,
        )

    def add_loan(self, loan: Loan) -> Loan:
        if is_supabase_session(self.db):
            return self.db.add(loan)
        self.db.add(loan)
        self.db.flush()
        return loan

    def add_installments(self, installments: list[LoanInstallment]) -> list[LoanInstallment]:
        if is_supabase_session(self.db):
            saved_installments: list[LoanInstallment] = []
            for installment in installments:
                try:
                    saved_installments.append(self.db.add(installment))
                except RuntimeError as exc:
                    if self._is_missing_supabase_table(exc, LoanInstallment):
                        return saved_installments or installments
                    raise
            return saved_installments
        self.db.add_all(installments)
        self.db.flush()
        return installments

    def delete_installments(self, installments: list[LoanInstallment]) -> None:
        if not installments:
            return
        if is_supabase_session(self.db):
            for installment in installments:
                try:
                    self.db.delete(installment)
                except RuntimeError as exc:
                    if self._is_missing_supabase_table(exc, LoanInstallment):
                        return
                    raise
            return
        for installment in installments:
            self.db.delete(installment)
        self.db.flush()

    def add_loan_payment(self, payment: LoanPayment) -> LoanPayment:
        if is_supabase_session(self.db):
            try:
                return self.db.add(payment)
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, LoanPayment):
                    return payment
                raise
        self.db.add(payment)
        self.db.flush()
        return payment

    def get_loan_by_id(self, loan_id: uuid.UUID) -> Loan | None:
        if is_supabase_session(self.db):
            return self._normalize_loan(self.db.get(Loan, loan_id))
        return self.db.get(Loan, loan_id)

    def get_loan_by_application(self, application_id: uuid.UUID) -> Loan | None:
        if is_supabase_session(self.db):
            return self._normalize_loan(self.db.fetch_one(Loan, {"application_id": f"eq.{application_id}"}))
        return self.db.scalar(select(Loan).where(Loan.application_id == application_id))

    def list_loans_for_user(self, user_id: uuid.UUID) -> list[Loan]:
        if is_supabase_session(self.db):
            loans = self.db.fetch_many(Loan, {"user_id": f"eq.{user_id}", "order": "created_at.desc"})
            return [self._normalize_loan(loan) for loan in loans if loan is not None]
        stmt = select(Loan).where(Loan.user_id == user_id).order_by(Loan.created_at.desc())
        return list(self.db.scalars(stmt))

    def list_installments_for_loan(self, loan_id: uuid.UUID) -> list[LoanInstallment]:
        if is_supabase_session(self.db):
            try:
                return self.db.fetch_many(
                    LoanInstallment,
                    {"loan_id": f"eq.{loan_id}", "order": "installment_number.asc"},
                )
            except RuntimeError as exc:
                if self._is_missing_supabase_table(exc, LoanInstallment):
                    return []
                raise
        stmt = (
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan_id)
            .order_by(LoanInstallment.installment_number.asc())
        )
        return list(self.db.scalars(stmt))

    def _is_missing_supabase_table(self, exc: RuntimeError, model: type[object]) -> bool:
        return f"Could not find the table 'public.{model.__tablename__}'" in str(exc)

    def _is_supabase_document_storage_error(self, exc: RuntimeError) -> bool:
        detail = str(exc)
        return self._is_missing_supabase_table(exc, CreditDocument) or any(
            marker in detail
            for marker in (
                "credit_documents.application_id",
                "credit_documents.content_base64",
                "Could not find the 'application_id' column of 'credit_documents'",
                "Could not find the 'content_base64' column of 'credit_documents'",
            )
        )
