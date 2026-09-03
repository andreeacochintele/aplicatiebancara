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
from typing import Annotated, Literal

from pydantic import BaseModel, Field

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
class LoanPaymentConfirmCard(BaseModel):
    kind: Literal["loan_payment_confirm"] = "loan_payment_confirm"
    action_id: uuid.UUID
    title: str
    amount: str
    currency: str
    source_wallet_label: str
    outstanding_principal: str
    next_payment_date: str | None = None
    expires_at: datetime


class CreditCardRepaymentConfirmCard(BaseModel):
    kind: Literal["credit_card_repayment_confirm"] = "credit_card_repayment_confirm"
    action_id: uuid.UUID
    card_label: str
    amount: str
    currency: str
    source_wallet_label: str
    balance_due: str
    expires_at: datetime


class CreditCardCollateralOption(BaseModel):
    wallet_id: uuid.UUID
    kind: Literal["current_account", "debit_card"]
    label: str


class CreditCardGenerationConfirmCard(BaseModel):
    kind: Literal["credit_card_generation_confirm"] = "credit_card_generation_confirm"
    action_id: uuid.UUID
    card_label: str
    tier: str
    currency: str
    credit_limit: str
    collateral_wallet_id: uuid.UUID | None = None
    collateral_wallet_label: str | None = None
    collateral_options: list[CreditCardCollateralOption] = []
    expires_at: datetime


class WalletCurrencyOption(BaseModel):
    currency: str
    label: str


class WalletGenerationConfirmCard(BaseModel):
    kind: Literal["wallet_generation_confirm"] = "wallet_generation_confirm"
    action_id: uuid.UUID
    wallet_label: str
    currency: str | None = None
    currency_options: list[WalletCurrencyOption] = []
    expires_at: datetime


ActionCard = Annotated[
    PhoneTransferConfirmCard
    | LoanPaymentConfirmCard
    | CreditCardRepaymentConfirmCard
    | CreditCardGenerationConfirmCard
    | WalletGenerationConfirmCard,
    Field(discriminator="kind"),
]


class DownloadAttachment(BaseModel):
    """A file the frontend can fetch and save. `url` always points at an
    existing, already-authenticated REST endpoint (e.g. GET
    /statements/export) that the agent's tool call already used to produce
    the data being summarized — the agent never generates a file itself,
    only hands back a reference to the same deterministic export any page
    can already trigger. Relative to the API base, same as every other
    frontend apiRequest() path."""

    url: str


@dataclass
class AgentResult:
    """What an orchestrator-registered agent may return instead of a bare
    `str`. `ai/orchestrator/service.py` unwraps this; the three read-only
    agents keep returning plain strings and are untouched."""

    reply: str
    action_card: ActionCard | None = None
    download: DownloadAttachment | None = None


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


class CreditCardCollateralSelection(BaseModel):
    wallet_id: uuid.UUID


class WalletCurrencySelection(BaseModel):
    currency: str
