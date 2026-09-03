"""AgentAction — a single action the Actions Agent prepared from a chat
message and is holding for the user's explicit confirmation.

The row IS the audit trail for agent-initiated actions (there is no
admin_audit_logs entry — that table is for admin actions). `payload` holds
the fully-resolved, already-validated draft (recipient user id, amount as a
string, source wallet id, display fields) so confirm() never has to trust
anything the chat message said.

`status` is a real Postgres enum (a genuine state machine), unlike the
free-string `type` — a new action `type` shouldn't need a migration, but a
new *status* is a deliberate lifecycle change and should.

    DRAFT ──accept──► CONFIRMED ──ok──► EXECUTED
      │                   └──transfer error──► FAILED
      │                   └──fraud screen────► NEEDS_REVIEW
      ├──expiry (lazy, checked on confirm)──► EXPIRED
      ├──user cancels──────────────────────► CANCELLED
      └──newer draft in same conversation──► SUPERSEDED
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class AgentActionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


ACTION_TYPE_PHONE_TRANSFER = "phone_transfer"
ACTION_TYPE_LOAN_PAYMENT = "loan_payment"
ACTION_TYPE_CREDIT_CARD_REPAYMENT = "credit_card_repayment"


class AgentAction(Base):
    __tablename__ = "ai_agent_actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ai_agent_actions_idempotency_key"),
        Index("ix_ai_agent_actions_user_created", "user_id", "created_at"),
        Index("ix_ai_agent_actions_conversation", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_conversations.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[AgentActionStatus] = mapped_column(
        Enum(AgentActionStatus, name="ai_agent_action_status"),
        default=AgentActionStatus.DRAFT,
        nullable=False,
    )
    # Resolved + validated draft. Amounts are stored as strings, never floats.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # A random key minted per draft; the unique constraint plus the status
    # guard in confirm() makes a double-click / retry a no-op instead of a
    # second transfer.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
