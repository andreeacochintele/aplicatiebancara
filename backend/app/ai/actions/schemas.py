"""Wire types for the Actions Agent.

`ActionCard` is a closed catalog of UI components the frontend knows how to
render (one member today). The LLM never produces one of these and never
produces UI markup — the backend builds the card from fully-resolved,
already-validated data. Adding a new action type means adding a new member
here and a matching React component, not letting the model emit arbitrary UI.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.ai.actions.models import AgentActionStatus


class PhoneTransferConfirmCard(BaseModel):
    kind: Literal["phone_transfer_confirm"] = "phone_transfer_confirm"
    action_id: uuid.UUID
    recipient_name: str
    recipient_phone_masked: str | None
    amount: str
    currency: str
    source_wallet_label: str
    expires_at: datetime


# Closed union — extend with `Annotated[X | Y, Field(discriminator="kind")]`
# once there's a second member.
ActionCard = PhoneTransferConfirmCard


@dataclass
class AgentResult:
    """What an orchestrator-registered agent may return instead of a bare
    `str`. `ai/orchestrator/service.py` unwraps this; the three read-only
    agents keep returning plain strings and are untouched."""

    reply: str
    action_card: ActionCard | None = None


class AgentActionResultPublic(BaseModel):
    """Outcome of confirm/cancel and the GET poll — the frontend flips the
    card into a terminal state from `status`."""

    action_id: uuid.UUID
    type: str
    status: AgentActionStatus
    result_transaction_id: uuid.UUID | None = None
    error_code: str | None = None
    error_detail: str | None = None
    card: ActionCard | None = None
