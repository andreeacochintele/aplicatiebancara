"""Deterministic core of the Actions Agent: build a transfer draft, then
confirm/execute it. No LLM in here at all — the agent does one extraction
call and hands the parsed fields to prepare_phone_transfer().

Every figure the user confirms is re-derived here from verified data
(beneficiary row, wallet balance), never trusted from the chat message.
confirm() takes only an action_id and re-validates from scratch.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.ai.actions.fraud_screen import screen_transfer
from app.ai.actions.models import ACTION_TYPE_PHONE_TRANSFER, AgentAction, AgentActionStatus
from app.ai.actions.recipient_resolver import match_beneficiaries
from app.ai.actions.repository import AgentActionRepository
from app.ai.actions.schemas import AgentActionResultPublic, AgentResult, PhoneTransferConfirmCard
from app.ai.observability import log_event
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.payments.repository import BeneficiaryRepository
from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.repository import UserRepository
from app.wallets.models import WalletStatus
from app.wallets.repository import WalletRepository

MAX_TRANSFER_AMOUNT = Decimal("500.00")
DRAFT_TTL = timedelta(minutes=5)
SUPPORTED_CURRENCY = "RON"
_CENTS = Decimal("0.01")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    return f"••• {digits[-3:]}" if len(digits) >= 3 else "•••"


def _mask_iban(iban: str | None) -> str | None:
    if not iban:
        return None
    tail = iban.strip()[-4:]
    return f"IBAN ···{tail}" if tail else "IBAN ···"


class ActionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AgentActionRepository(db)
        self.beneficiaries = BeneficiaryRepository(db)
        self.wallets = WalletRepository(db)
        self.users = UserRepository(db)

    # ---- draft ----

    def prepare_phone_transfer(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        amount_raw: str | None,
        currency_raw: str | None,
        recipient_name: str | None,
    ) -> AgentResult:
        currency = (currency_raw or SUPPORTED_CURRENCY).strip().upper()
        if currency != SUPPORTED_CURRENCY:
            return AgentResult(reply="Pot pregăti doar transferuri în RON deocamdată.")

        amount = self._parse_amount(amount_raw)
        if amount is None:
            return AgentResult(reply="Ce sumă vrei să trimiți? Spune-mi suma în RON.")
        if amount <= 0:
            return AgentResult(reply="Suma trebuie să fie mai mare ca zero.")
        if amount > MAX_TRANSFER_AMOUNT:
            return AgentResult(
                reply=(
                    "Pot pregăti prin chat transferuri de cel mult 500 RON. "
                    "Pentru o sumă mai mare, folosește pagina Payments."
                )
            )

        if not recipient_name or not recipient_name.strip():
            return AgentResult(reply="Către cine să trimit? Spune-mi numele unui beneficiar salvat.")

        beneficiaries = self.beneficiaries.list_for_owner(user_id)
        matches = match_beneficiaries(recipient_name, beneficiaries)
        if not matches:
            return AgentResult(
                reply=(
                    f"Nu am găsit un beneficiar pe nume «{recipient_name.strip()}». "
                    "Adaugă-l întâi în Payments → Beneficiaries și încearcă din nou."
                )
            )
        if len(matches) > 1:
            names = ", ".join(sorted(b.name for b in matches))
            return AgentResult(reply=f"Am găsit mai mulți beneficiari: {names}. Spune-mi numele complet.")

        beneficiary = matches[0]

        source = self.wallets.get_by_user_and_currency(user_id, SUPPORTED_CURRENCY)
        if source is None:
            return AgentResult(reply="Nu ai un portofel RON din care să trimit.")
        if source.status != WalletStatus.ACTIVE:
            return AgentResult(reply=f"Portofelul tău RON este {source.status.value.lower()}.")

        resolved = self._resolve_destination(user_id, beneficiary, source)
        if isinstance(resolved, str):
            return AgentResult(reply=resolved)
        recipient_user_id, destination, contact_masked = resolved

        if source.available_balance < amount:
            return AgentResult(
                reply=(
                    f"Sold insuficient: ai {source.available_balance} RON, "
                    f"iar transferul e de {amount} RON."
                )
            )

        self._supersede_open_drafts(conversation_id)

        source_label = f"RON — sold {source.available_balance}"
        action = self.repository.add(
            AgentAction(
                user_id=user_id,
                conversation_id=conversation_id,
                type=ACTION_TYPE_PHONE_TRANSFER,
                status=AgentActionStatus.DRAFT,
                payload={
                    "amount": f"{amount:.2f}",
                    "currency": SUPPORTED_CURRENCY,
                    "recipient_user_id": str(recipient_user_id),
                    "recipient_beneficiary_id": str(beneficiary.id),
                    "recipient_display_name": beneficiary.name,
                    "recipient_phone_masked": contact_masked,
                    "source_wallet_id": str(source.id),
                    "destination_wallet_id": str(destination.id),
                    "source_wallet_label": source_label,
                },
                idempotency_key=uuid.uuid4().hex,
                expires_at=_now() + DRAFT_TTL,
            )
        )
        self.repository.flush()
        log_event(
            "agent_action_drafted",
            action_id=str(action.id),
            type=action.type,
            amount=f"{amount:.2f}",
            currency=SUPPORTED_CURRENCY,
        )
        return AgentResult(
            reply="Am pregătit transferul. Verifică detaliile și apasă Accept pentru a-l trimite.",
            action_card=self._card(action),
        )

    # ---- confirm / cancel / read ----

    def confirm(self, user_id: uuid.UUID, action_id: uuid.UUID) -> AgentActionResultPublic:
        action = self._get_owned(user_id, action_id)

        if action.status == AgentActionStatus.EXECUTED:
            return self._public(action)  # idempotent replay of a double-click
        if action.status == AgentActionStatus.CONFIRMED:
            raise ConflictError("Acțiunea este deja în curs de procesare.")
        if action.status != AgentActionStatus.DRAFT:
            raise ConflictError(f"Acțiunea este {action.status.value.lower()}.")

        if _as_aware_utc(action.expires_at) < _now():
            action.status = AgentActionStatus.EXPIRED
            self.db.commit()  # persist despite the 409 below — same pattern as PaymentRequestService
            raise ConflictError("Draftul a expirat. Cere transferul din nou.")

        payload = action.payload
        amount = Decimal(payload["amount"])
        if amount > MAX_TRANSFER_AMOUNT:
            return self._fail(action, "LIMIT_EXCEEDED", "Suma depășește limita de 500 RON.")

        recipient = self.users.get_by_id(uuid.UUID(payload["recipient_user_id"]))
        beneficiary = self.beneficiaries.get_owned_by_id(user_id, uuid.UUID(payload["recipient_beneficiary_id"]))
        if recipient is None or beneficiary is None:
            return self._fail(action, "RECIPIENT_GONE", "Beneficiarul nu mai există.")

        source = self.wallets.get_by_id(uuid.UUID(payload["source_wallet_id"]))
        if source is None or source.user_id != user_id or source.status != WalletStatus.ACTIVE:
            return self._fail(action, "SOURCE_UNAVAILABLE", "Portofelul sursă nu mai este disponibil.")

        destination = self.wallets.get_by_id(uuid.UUID(payload["destination_wallet_id"]))
        if destination is None or destination.user_id != recipient.id:
            return self._fail(action, "DESTINATION_UNAVAILABLE", "Portofelul destinatarului nu mai este disponibil.")

        if source.available_balance < amount:
            return self._fail(action, "INSUFFICIENT_FUNDS", "Sold insuficient pentru acest transfer.")

        recent_executed = self.repository.count_recent_executed(user_id)
        screen = screen_transfer(self.db, user_id, recent_executed)
        if screen.blocked:
            action.status = AgentActionStatus.NEEDS_REVIEW
            action.error_code = "FRAUD_REVIEW"
            action.error_detail = "Verificare de siguranță necesară — continuă din pagina Payments."
            self.repository.flush()
            return self._public(action)

        action.status = AgentActionStatus.CONFIRMED
        action.confirmed_at = _now()
        self.repository.flush()

        try:
            transaction = TransactionService(self.db).create_internal_transfer(
                user_id,
                InternalTransferCreate(
                    source_wallet_id=source.id,
                    destination_wallet_id=destination.id,
                    amount=amount,
                    description=f"Transfer către {beneficiary.name} (asistent Nova)",
                ),
            )
        except DomainError as exc:
            return self._fail(action, "TRANSFER_FAILED", str(exc))

        action.status = AgentActionStatus.EXECUTED
        action.result_transaction_id = transaction.id
        action.executed_at = _now()
        self.repository.flush()
        log_event(
            "agent_action_executed",
            action_id=str(action.id),
            transaction_id=str(transaction.id),
        )
        return self._public(action)

    def cancel(self, user_id: uuid.UUID, action_id: uuid.UUID) -> AgentActionResultPublic:
        action = self._get_owned(user_id, action_id)
        if action.status == AgentActionStatus.CANCELLED:
            return self._public(action)
        if action.status != AgentActionStatus.DRAFT:
            raise ConflictError(f"Acțiunea este {action.status.value.lower()} și nu poate fi anulată.")
        action.status = AgentActionStatus.CANCELLED
        self.repository.flush()
        return self._public(action)

    def get(self, user_id: uuid.UUID, action_id: uuid.UUID) -> AgentActionResultPublic:
        action = self._get_owned(user_id, action_id)
        if action.status == AgentActionStatus.DRAFT and _as_aware_utc(action.expires_at) < _now():
            action.status = AgentActionStatus.EXPIRED
            self.db.commit()
        return self._public(action)

    # ---- helpers ----

    def _get_owned(self, user_id: uuid.UUID, action_id: uuid.UUID) -> AgentAction:
        action = self.repository.get_by_id(action_id)
        if action is None or action.user_id != user_id:
            raise NotFoundError("Action not found")
        return action

    def _resolve_recipient_user(self, beneficiary):
        if beneficiary.beneficiary_user_id is not None:
            return self.users.get_by_id(beneficiary.beneficiary_user_id)
        if beneficiary.phone:
            return self.users.get_by_phone(beneficiary.phone)
        return None

    def _resolve_destination(self, sender_id, beneficiary, source):
        """Turn a matched beneficiary into (recipient_user_id, destination
        Wallet, masked-contact) — or a plain string with the reason it
        can't be done. Tries a linked app user / saved phone first, then an
        on-us (in-app) IBAN. An external IBAN is not supported through chat
        yet — the user is told to use the Payments page for a standard bank
        transfer."""
        recipient = self._resolve_recipient_user(beneficiary)
        if recipient is not None:
            if recipient.id == sender_id:
                return "Nu îți poți trimite bani ție însuți."
            destination = self.wallets.get_by_user_and_currency(recipient.id, SUPPORTED_CURRENCY)
            if destination is None:
                return f"«{beneficiary.name}» nu are un portofel RON."
            return recipient.id, destination, _mask_phone(recipient.phone or beneficiary.phone)

        if beneficiary.iban:
            destination = self.wallets.get_by_iban(beneficiary.iban.strip())
            if destination is None:
                return (
                    f"«{beneficiary.name}» are un IBAN extern. Prin chat pot trimite doar "
                    "către conturi din aplicație — folosește pagina Payments pentru un "
                    "transfer bancar standard."
                )
            if destination.id == source.id or destination.user_id == sender_id:
                return "Nu îți poți trimite bani ție însuți."
            if destination.currency != SUPPORTED_CURRENCY:
                return f"«{beneficiary.name}» are un cont în {destination.currency}, nu în RON."
            if destination.status != WalletStatus.ACTIVE:
                return f"Contul lui «{beneficiary.name}» este {destination.status.value.lower()}."
            return destination.user_id, destination, _mask_iban(beneficiary.iban)

        return f"«{beneficiary.name}» nu are un telefon sau un cont din aplicație pe care să trimit."

    def _supersede_open_drafts(self, conversation_id: uuid.UUID | None) -> None:
        if conversation_id is None:
            return
        for stale in self.repository.list_open_drafts_for_conversation(conversation_id):
            stale.status = AgentActionStatus.SUPERSEDED
        self.repository.flush()

    def _parse_amount(self, amount_raw: str | None) -> Decimal | None:
        if amount_raw is None:
            return None
        text = str(amount_raw).strip().replace(",", ".")
        if not text:
            return None
        try:
            return Decimal(text).quantize(_CENTS, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return None

    def _fail(self, action: AgentAction, code: str, detail: str) -> AgentActionResultPublic:
        action.status = AgentActionStatus.FAILED
        action.error_code = code
        action.error_detail = detail[:255]
        self.repository.flush()
        log_event("agent_action_failed", action_id=str(action.id), error_code=code)
        return self._public(action)

    def _card(self, action: AgentAction) -> PhoneTransferConfirmCard:
        p = action.payload
        return PhoneTransferConfirmCard(
            action_id=action.id,
            recipient_name=p["recipient_display_name"],
            recipient_phone_masked=p.get("recipient_phone_masked"),
            amount=p["amount"],
            currency=p["currency"],
            source_wallet_label=p["source_wallet_label"],
            expires_at=action.expires_at,
        )

    def public_view(self, action: AgentAction) -> AgentActionResultPublic:
        """Public projection of a raw AgentAction row — for callers outside
        this module (the orchestrator embeds it into the message list)."""
        return self._public(action)

    def _public(self, action: AgentAction) -> AgentActionResultPublic:
        # `card` is always the display data (recipient / amount / wallet) —
        # `status` is what tells the UI whether it's still actionable. The
        # UI needs both to re-draw the card in any state after a
        # conversation is reopened.
        return AgentActionResultPublic(
            action_id=action.id,
            type=action.type,
            status=action.status,
            result_transaction_id=action.result_transaction_id,
            error_code=action.error_code,
            error_detail=action.error_detail,
            card=self._card(action),
        )
