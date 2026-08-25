"""Credit endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.core.exceptions import ValidationError
from app.credit.models import CreditApplicationType
from app.credit.schemas import (
    CreditApplicationCreate,
    CreditApplicationDecision,
    CreditApplicationPublic,
    CreditDocumentContentPublic,
    CreditDocumentCreate,
    CreditDocumentPublic,
    CreditDocumentReview,
    CreditProfilePublic,
    CreditScorePublic,
    CreditScoreRecalculateRequest,
    EarlyRepaymentPaymentRequest,
    EarlyRepaymentPaymentResult,
    EarlyRepaymentResult,
    EarlyRepaymentSimulationRequest,
    LoanCalculatorRequest,
    LoanCalculatorResult,
    LoanInstallmentPublic,
    LoanProductPublic,
    LoanPublic,
)
from app.credit.service import CreditService
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/credit", tags=["credit"])


@router.get("/profile", response_model=CreditProfilePublic)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditProfilePublic:
    profile = CreditService(db).get_or_create_profile(current_user.id)
    db.commit()
    return profile


@router.get("/score", response_model=CreditScorePublic)
def get_score(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditScorePublic:
    score = CreditService(db).get_score(current_user.id)
    db.commit()
    return score


@router.post("/score/recalculate", response_model=CreditScorePublic)
def recalculate_score(
    payload: CreditScoreRecalculateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditScorePublic:
    score = CreditService(db).recalculate_score(current_user.id, payload)
    db.commit()
    return score


@router.post("/loan-calculator", response_model=LoanCalculatorResult)
def calculate_loan(
    payload: LoanCalculatorRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanCalculatorResult:
    return CreditService(db).calculate_loan(payload)


@router.get("/loan-products", response_model=list[LoanProductPublic])
def list_loan_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LoanProductPublic]:
    return CreditService(db).list_loan_products()


@router.get("/applications", response_model=list[CreditApplicationPublic])
def list_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CreditApplicationPublic]:
    return CreditService(db).list_applications(current_user.id)


@router.post("/applications", response_model=CreditApplicationPublic, status_code=201)
def create_application(
    payload: CreditApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditApplicationPublic:
    if payload.type == CreditApplicationType.PERSONAL_LOAN and not payload.documents:
        raise ValidationError("Loan applications require supporting documents")
    application = CreditService(db).create_application(current_user.id, payload)
    db.commit()
    return application


@router.get("/documents", response_model=list[CreditDocumentPublic])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CreditDocumentPublic]:
    return CreditService(db).list_documents(current_user.id)


@router.post("/documents", response_model=CreditDocumentPublic, status_code=201)
def upload_document(
    payload: CreditDocumentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditDocumentPublic:
    document = CreditService(db).upload_document(current_user.id, payload)
    db.commit()
    return document


@router.get("/documents/{document_id}/content", response_model=CreditDocumentContentPublic)
def get_document_content(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditDocumentContentPublic:
    return CreditService(db).get_document_content_for_user(current_user.id, document_id)


@router.get("/admin/applications", response_model=list[CreditApplicationPublic])
def list_all_applications(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CreditApplicationPublic]:
    return CreditService(db).list_all_applications_with_documents()


@router.get("/admin/documents", response_model=list[CreditDocumentPublic])
def list_all_documents(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CreditDocumentPublic]:
    return CreditService(db).list_all_documents()


@router.get("/admin/documents/{document_id}/content", response_model=CreditDocumentContentPublic)
def get_admin_document_content(
    document_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CreditDocumentContentPublic:
    return CreditService(db).get_document_content_for_admin(document_id)


@router.patch("/admin/documents/{document_id}/review", response_model=CreditDocumentPublic)
def review_document(
    document_id: uuid.UUID,
    payload: CreditDocumentReview,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CreditDocumentPublic:
    document = CreditService(db).review_document(document_id, admin.id, payload)
    db.commit()
    return document


@router.patch("/admin/applications/{application_id}/decision", response_model=CreditApplicationPublic)
def decide_application(
    application_id: uuid.UUID,
    payload: CreditApplicationDecision,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CreditApplicationPublic:
    service = CreditService(db)
    service.decide_application(application_id, payload, admin_id=admin.id)
    db.commit()
    return service.get_application_public(application_id)


@router.get("/loans", response_model=list[LoanPublic])
def list_loans(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LoanPublic]:
    loans = CreditService(db).list_loans(current_user.id)
    db.commit()
    return loans


@router.post("/applications/{application_id}/loan", response_model=LoanPublic, status_code=201)
def create_loan_from_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPublic:
    loan = CreditService(db).create_loan_from_application(current_user.id, application_id)
    db.commit()
    return loan


@router.get("/loans/{loan_id}", response_model=LoanPublic)
def get_loan(
    loan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoanPublic:
    return CreditService(db).get_loan_for_user(current_user.id, loan_id)


@router.get("/loans/{loan_id}/installments", response_model=list[LoanInstallmentPublic])
def list_loan_installments(
    loan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LoanInstallmentPublic]:
    return CreditService(db).list_installments_for_loan(current_user.id, loan_id)


@router.post("/loans/{loan_id}/early-repayment-simulation", response_model=EarlyRepaymentResult)
def simulate_early_repayment(
    loan_id: uuid.UUID,
    payload: EarlyRepaymentSimulationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EarlyRepaymentResult:
    return CreditService(db).simulate_early_repayment(
        current_user.id,
        loan_id,
        payload.extra_payment_amount,
    )


@router.post("/loans/{loan_id}/early-repayment", response_model=EarlyRepaymentPaymentResult)
def make_early_repayment(
    loan_id: uuid.UUID,
    payload: EarlyRepaymentPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EarlyRepaymentPaymentResult:
    result = CreditService(db).make_early_repayment(
        current_user.id,
        loan_id,
        payload.source_wallet_id,
        payload.amount,
        payload.source_card_id,
    )
    db.commit()
    return result


@router.get("/applications/{application_id}", response_model=CreditApplicationPublic)
def get_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditApplicationPublic:
    return CreditService(db).get_application_for_user(current_user.id, application_id)
