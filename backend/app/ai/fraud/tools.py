"""Typed, read-only tools for the Fraud Investigation Agent.

Every tool wraps FraudService/TransactionRepository — never touches the DB
directly (architecture.md §44):

    Agent -> Tool -> Backend Service -> Database

Unlike the three orchestrator-registered agents' tools
(ai/personal_finance/tools.py, ai/credit/tools.py), these don't take a
fixed "current user" ToolContext (ai/tools/base.py): this agent is invoked
by an admin investigating one specific fraud case, not by the case's own
user, so each tool takes whichever id it actually needs (case_id,
transaction_id, user_id) explicitly rather than assuming a single implicit
user for the whole call.

None of these ever write anything — this agent is advisory-only and must
never mutate a case's risk_score, status, or decision (see
ai/fraud/agent.py's module docstring).
"""
import uuid

from sqlalchemy.orm import Session

from app.ai.observability import log_tool_call
from app.auth.models import UserDevice
from app.fraud.schemas import FraudCaseDetail, FraudFlagPublic
from app.fraud.service import FraudService, SpendingProfile
from app.transactions.models import Transaction
from app.transactions.repository import TransactionRepository


@log_tool_call
def get_case(db: Session, case_id: uuid.UUID) -> FraudCaseDetail:
    service = FraudService(db)
    return service.to_detail(service.get_case(case_id))


@log_tool_call
def get_transaction(db: Session, transaction_id: uuid.UUID) -> Transaction | None:
    return TransactionRepository(db).get_by_id(transaction_id)


@log_tool_call
def get_user_transaction_history(db: Session, user_id: uuid.UUID) -> list[Transaction]:
    return TransactionRepository(db).list_for_user(user_id)


@log_tool_call
def get_known_devices(db: Session, user_id: uuid.UUID) -> list[UserDevice]:
    return FraudService(db).get_known_devices(user_id)


@log_tool_call
def get_recent_activity(db: Session, user_id: uuid.UUID) -> list[Transaction]:
    return FraudService(db).get_recent_activity(user_id)


@log_tool_call
def get_fraud_flags(db: Session, case_id: uuid.UUID) -> list[FraudFlagPublic]:
    service = FraudService(db)
    return service.to_detail(service.get_case(case_id)).flags


@log_tool_call
def get_user_spending_profile(db: Session, user_id: uuid.UUID) -> SpendingProfile:
    return FraudService(db).get_user_spending_profile(user_id)
