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
from app.ai.actions.models import (
    ACTION_TYPE_CREDIT_CARD_GENERATION,
    ACTION_TYPE_CREDIT_CARD_REPAYMENT,
    ACTION_TYPE_LOAN_PAYMENT,
    ACTION_TYPE_PHONE_TRANSFER,
    ACTION_TYPE_WALLET_GENERATION,
    AgentAction,
    AgentActionStatus,
)
from app.ai.actions.recipient_resolver import match_beneficiaries
from app.ai.actions.repository import AgentActionRepository
from app.ai.actions.schemas import (
    AgentActionResultPublic,
    AgentResult,
    CreditCardGenerationConfirmCard,
    CreditCardRepaymentConfirmCard,
    LoanPaymentConfirmCard,
    PhoneTransferConfirmCard,
    WalletGenerationConfirmCard,
)
from app.ai.observability import log_event
from app.cards.models import CardStatus, CardTier, CardType
from app.cards.repository import CardRepository
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.credit.models import LoanInstallmentStatus, LoanStatus
from app.credit.service import CreditService
from app.payments.repository import BeneficiaryRepository
from app.transactions.schemas import CreditCardRepaymentCreate, InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.repository import UserRepository
from app.wallets.models import WalletStatus
from app.wallets.repository import WalletRepository
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService

MAX_TRANSFER_AMOUNT = Decimal("500.00")
DRAFT_TTL = timedelta(minutes=5)
SUPPORTED_CURRENCY = "RON"
_CENTS = Decimal("0.01")
WALLET_CURRENCY_OPTIONS = ("RON", "EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "PLN", "TRY")


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
        self.cards = CardRepository(db)

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

    def prepare_loan_payment(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        amount_raw: str | None,
        mode_raw: str | None,
    ) -> AgentResult:
        credit = CreditService(self.db)
        loans = [loan for loan in credit.list_loans(user_id) if loan.status == LoanStatus.ACTIVE]
        if not loans:
            return AgentResult(reply="Nu ai niciun imprumut activ de platit.")
        if len(loans) > 1:
            return AgentResult(
                reply="Ai mai multe imprumuturi active. Deschide Credit si alege imprumutul pe care vrei sa-l platesti."
            )

        loan = loans[0]
        mode = "early_repayment" if mode_raw == "early_repayment" or amount_raw is not None else "regular_installment"
        amount = self._parse_amount(amount_raw)
        next_payment_date = None
        if mode == "regular_installment":
            pending = [
                item
                for item in credit.repository.list_installments_for_loan(loan.id)
                if item.status == LoanInstallmentStatus.PENDING
            ]
            if not pending:
                return AgentResult(reply="Imprumutul nu are rate ramase de platit.")
            amount = pending[0].payment_amount
            next_payment_date = pending[0].due_date.isoformat()
            title = "Rata lunara pentru imprumut"
        else:
            if amount is None:
                return AgentResult(reply="Ce suma vrei sa rambursezi anticipat?")
            if amount <= 0:
                return AgentResult(reply="Suma trebuie sa fie mai mare ca zero.")
            simulation = credit.simulate_early_repayment(user_id, loan.id, amount)
            amount = simulation.applied_extra_payment_amount
            title = "Rambursare anticipata imprumut"

        source = self._select_source_wallet(user_id, loan.currency, amount)
        if isinstance(source, str):
            return AgentResult(reply=source)

        self._supersede_open_drafts(conversation_id)
        action = self.repository.add(
            AgentAction(
                user_id=user_id,
                conversation_id=conversation_id,
                type=ACTION_TYPE_LOAN_PAYMENT,
                status=AgentActionStatus.DRAFT,
                payload={
                    "loan_id": str(loan.id),
                    "mode": mode,
                    "title": title,
                    "amount": f"{amount:.2f}",
                    "currency": loan.currency,
                    "source_wallet_id": str(source.id),
                    "source_wallet_label": self._wallet_label(source),
                    "outstanding_principal": f"{loan.outstanding_principal:.2f}",
                    "next_payment_date": next_payment_date,
                },
                idempotency_key=uuid.uuid4().hex,
                expires_at=_now() + DRAFT_TTL,
            )
        )
        self.repository.flush()
        return AgentResult(
            reply="Am pregatit plata pentru imprumut. Verifica detaliile si apasa Accept ca sa o execut.",
            action_card=self._card(action),
        )

    def prepare_credit_card_repayment(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        amount_raw: str | None,
        card_last_four: str | None,
    ) -> AgentResult:
        cards = [
            card
            for card in self.cards.list_for_user(user_id)
            if card.type == CardType.CREDIT and card.status == CardStatus.ACTIVE
        ]
        if card_last_four:
            digits = "".join(ch for ch in card_last_four if ch.isdigit())
            cards = [card for card in cards if card.last_four == digits[-4:]]

        owing = []
        for card in cards:
            account = self.cards.get_credit_account(card.id)
            if account is not None and account.used_amount > 0:
                owing.append((card, account))
        if not owing:
            return AgentResult(reply="Nu am gasit un card de credit activ cu sold de plata.")
        if len(owing) > 1:
            labels = ", ".join(f"**** {card.last_four}" for card, _account in owing)
            return AgentResult(reply=f"Ai mai multe carduri de credit cu sold: {labels}. Spune ultimele 4 cifre.")

        card, account = owing[0]
        amount = self._parse_amount(amount_raw) or account.used_amount
        if amount <= 0:
            return AgentResult(reply="Suma trebuie sa fie mai mare ca zero.")
        if amount > account.used_amount:
            return AgentResult(reply=f"Suma este mai mare decat soldul cardului: {account.used_amount} {account.currency}.")

        source = self._select_source_wallet(user_id, account.currency, amount)
        if isinstance(source, str):
            return AgentResult(reply=source)

        self._supersede_open_drafts(conversation_id)
        action = self.repository.add(
            AgentAction(
                user_id=user_id,
                conversation_id=conversation_id,
                type=ACTION_TYPE_CREDIT_CARD_REPAYMENT,
                status=AgentActionStatus.DRAFT,
                payload={
                    "card_id": str(card.id),
                    "card_label": f"Credit **** {card.last_four}",
                    "amount": f"{amount:.2f}",
                    "currency": account.currency,
                    "source_wallet_id": str(source.id),
                    "source_wallet_label": self._wallet_label(source),
                    "balance_due": f"{account.used_amount:.2f}",
                },
                idempotency_key=uuid.uuid4().hex,
                expires_at=_now() + DRAFT_TTL,
            )
        )
        self.repository.flush()
        return AgentResult(
            reply="Am pregatit plata pentru cardul de credit. Verifica detaliile si apasa Accept ca sa o execut.",
            action_card=self._card(action),
        )

    def prepare_credit_card_generation(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        tier_raw: str | None,
        currency_raw: str | None,
        collateral_reference: str | None = None,
    ) -> AgentResult:
        tier = self._parse_card_tier(tier_raw)
        if tier is None:
            return AgentResult(reply="Pot genera carduri de credit Regular, Gold sau Platinum. Ce tip vrei?")

        currency = (currency_raw or SUPPORTED_CURRENCY).strip().upper()
        if currency in ("LEI", "RON."):
            currency = SUPPORTED_CURRENCY
        if len(currency) != 3:
            return AgentResult(reply="Spune-mi moneda pentru card ca un cod de 3 litere, de exemplu RON.")

        limit = CardService.CREDIT_LIMITS[tier]
        options = self._credit_card_collateral_options(user_id, currency, limit)
        if not options:
            return AgentResult(
                reply=(
                    f"Nu am gasit un cont {currency} care are cel putin {limit:.2f} {currency} "
                    "pentru garantia cardului de credit."
                )
            )
        source = None
        if collateral_reference and str(collateral_reference).strip():
            resolved = self._resolve_credit_card_collateral(user_id, currency, limit, collateral_reference)
            if isinstance(resolved, str):
                return AgentResult(reply=resolved)
            source = resolved

        self._supersede_open_drafts(conversation_id)
        action = self.repository.add(
            AgentAction(
                user_id=user_id,
                conversation_id=conversation_id,
                type=ACTION_TYPE_CREDIT_CARD_GENERATION,
                status=AgentActionStatus.DRAFT,
                payload={
                    "tier": tier.value,
                    "currency": currency,
                    "credit_limit": f"{limit:.2f}",
                    "collateral_wallet_id": str(source.id) if source is not None else None,
                    "collateral_wallet_label": self._collateral_wallet_label(source) if source is not None else None,
                    "collateral_options": options,
                    "card_label": f"{tier.value.title()} credit card",
                },
                idempotency_key=uuid.uuid4().hex,
                expires_at=_now() + DRAFT_TTL,
            )
        )
        self.repository.flush()
        return AgentResult(
            reply=(
                "Am pregatit generarea cardului de credit. Alege garantia, verifica detaliile "
                "si apasa Accept ca sa il creez."
            ),
            action_card=self._card(action),
        )

    def prepare_wallet_generation(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        currency_raw: str | None,
    ) -> AgentResult:
        currency = self._parse_wallet_currency(currency_raw)
        self._supersede_open_drafts(conversation_id)
        action = self.repository.add(
            AgentAction(
                user_id=user_id,
                conversation_id=conversation_id,
                type=ACTION_TYPE_WALLET_GENERATION,
                status=AgentActionStatus.DRAFT,
                payload={
                    "currency": currency,
                    "wallet_label": f"{currency} current account" if currency else "New current account",
                    "currency_options": [
                        {"currency": option, "label": option}
                        for option in WALLET_CURRENCY_OPTIONS
                    ],
                },
                idempotency_key=uuid.uuid4().hex,
                expires_at=_now() + DRAFT_TTL,
            )
        )
        self.repository.flush()
        return AgentResult(
            reply="Alege moneda pentru contul curent, apoi apasa Accept ca sa il creez.",
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

        if action.type == ACTION_TYPE_PHONE_TRANSFER:
            return self._confirm_phone_transfer(action)
        if action.type == ACTION_TYPE_LOAN_PAYMENT:
            return self._confirm_loan_payment(action)
        if action.type == ACTION_TYPE_CREDIT_CARD_REPAYMENT:
            return self._confirm_credit_card_repayment(action)
        if action.type == ACTION_TYPE_CREDIT_CARD_GENERATION:
            return self._confirm_credit_card_generation(action)
        if action.type == ACTION_TYPE_WALLET_GENERATION:
            return self._confirm_wallet_generation(action)
        return self._fail(action, "UNSUPPORTED_ACTION", "Tipul actiunii nu mai este disponibil.")

    def _confirm_phone_transfer(self, action: AgentAction) -> AgentActionResultPublic:
        payload = action.payload
        amount = Decimal(payload["amount"])
        if amount > MAX_TRANSFER_AMOUNT:
            return self._fail(action, "LIMIT_EXCEEDED", "Suma depășește limita de 500 RON.")

        recipient = self.users.get_by_id(uuid.UUID(payload["recipient_user_id"]))
        beneficiary = self.beneficiaries.get_owned_by_id(action.user_id, uuid.UUID(payload["recipient_beneficiary_id"]))
        if recipient is None or beneficiary is None:
            return self._fail(action, "RECIPIENT_GONE", "Beneficiarul nu mai există.")

        source = self.wallets.get_by_id(uuid.UUID(payload["source_wallet_id"]))
        if source is None or source.user_id != action.user_id or source.status != WalletStatus.ACTIVE:
            return self._fail(action, "SOURCE_UNAVAILABLE", "Portofelul sursă nu mai este disponibil.")

        destination = self.wallets.get_by_id(uuid.UUID(payload["destination_wallet_id"]))
        if destination is None or destination.user_id != recipient.id:
            return self._fail(action, "DESTINATION_UNAVAILABLE", "Portofelul destinatarului nu mai este disponibil.")

        if source.available_balance < amount:
            return self._fail(action, "INSUFFICIENT_FUNDS", "Sold insuficient pentru acest transfer.")

        recent_executed = self.repository.count_recent_executed(action.user_id)
        screen = screen_transfer(self.db, action.user_id, recent_executed)
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
                action.user_id,
                InternalTransferCreate(
                    source_wallet_id=source.id,
                    destination_wallet_id=destination.id,
                    amount=amount,
                    description=f"Transfer către {beneficiary.name} (asistent Bumble-B)",
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

    def _confirm_loan_payment(self, action: AgentAction) -> AgentActionResultPublic:
        action.status = AgentActionStatus.CONFIRMED
        action.confirmed_at = _now()
        self.repository.flush()
        payload = action.payload
        try:
            if payload["mode"] == "regular_installment":
                result = CreditService(self.db).make_regular_installment_payment(
                    action.user_id,
                    uuid.UUID(payload["loan_id"]),
                    uuid.UUID(payload["source_wallet_id"]),
                )
                transaction_id = result.transaction_id
            else:
                result = CreditService(self.db).make_early_repayment(
                    action.user_id,
                    uuid.UUID(payload["loan_id"]),
                    uuid.UUID(payload["source_wallet_id"]),
                    Decimal(payload["amount"]),
                )
                transaction_id = result.transaction_id
        except DomainError as exc:
            return self._fail(action, "LOAN_PAYMENT_FAILED", str(exc))

        action.status = AgentActionStatus.EXECUTED
        action.result_transaction_id = transaction_id
        action.executed_at = _now()
        self.repository.flush()
        log_event("agent_action_executed", action_id=str(action.id), transaction_id=str(transaction_id))
        return self._public(action)

    def _confirm_credit_card_repayment(self, action: AgentAction) -> AgentActionResultPublic:
        action.status = AgentActionStatus.CONFIRMED
        action.confirmed_at = _now()
        self.repository.flush()
        payload = action.payload
        try:
            transaction = TransactionService(self.db).create_credit_card_repayment(
                action.user_id,
                CreditCardRepaymentCreate(
                    card_id=uuid.UUID(payload["card_id"]),
                    source_wallet_id=uuid.UUID(payload["source_wallet_id"]),
                    amount=Decimal(payload["amount"]),
                ),
            )
        except DomainError as exc:
            return self._fail(action, "CREDIT_CARD_REPAYMENT_FAILED", str(exc))

        action.status = AgentActionStatus.EXECUTED
        action.result_transaction_id = transaction.id
        action.executed_at = _now()
        self.repository.flush()
        log_event("agent_action_executed", action_id=str(action.id), transaction_id=str(transaction.id))
        return self._public(action)

    def _confirm_credit_card_generation(self, action: AgentAction) -> AgentActionResultPublic:
        action.status = AgentActionStatus.CONFIRMED
        action.confirmed_at = _now()
        self.repository.flush()
        payload = dict(action.payload)
        if not payload.get("collateral_wallet_id"):
            return self._fail(action, "COLLATERAL_REQUIRED", "Alege garantia inainte sa confirmi cardul.")
        try:
            card = CardService(self.db).create_card(
                action.user_id,
                CardCreate(
                    type=CardType.CREDIT,
                    tier=CardTier(payload["tier"]),
                    currency=payload["currency"],
                    collateral_wallet_id=uuid.UUID(payload["collateral_wallet_id"]),
                    collateral_amount=Decimal(payload["credit_limit"]),
                ),
                admin_approved=False,
            )
        except DomainError as exc:
            return self._fail(action, "CREDIT_CARD_GENERATION_FAILED", str(exc))

        payload["card_label"] = f"Credit **** {card.last_four}"
        action.payload = payload
        action.status = AgentActionStatus.EXECUTED
        action.executed_at = _now()
        self.repository.flush()
        log_event("agent_action_executed", action_id=str(action.id), card_id=str(card.id))
        return self._public(action)

    def _confirm_wallet_generation(self, action: AgentAction) -> AgentActionResultPublic:
        action.status = AgentActionStatus.CONFIRMED
        action.confirmed_at = _now()
        self.repository.flush()
        payload = dict(action.payload)
        currency = payload.get("currency")
        if not currency:
            return self._fail(action, "CURRENCY_REQUIRED", "Alege moneda inainte sa confirmi contul.")
        try:
            wallet = WalletService(self.db).create_wallet(action.user_id, WalletCreate(currency=currency))
        except DomainError as exc:
            return self._fail(action, "WALLET_GENERATION_FAILED", str(exc))

        payload["wallet_label"] = f"{wallet.currency} current account"
        action.payload = payload
        action.status = AgentActionStatus.EXECUTED
        action.executed_at = _now()
        self.repository.flush()
        log_event("agent_action_executed", action_id=str(action.id), wallet_id=str(wallet.id))
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

    def select_credit_card_collateral(
        self,
        user_id: uuid.UUID,
        action_id: uuid.UUID,
        wallet_id: uuid.UUID,
    ) -> AgentActionResultPublic:
        action = self._get_owned(user_id, action_id)
        if action.type != ACTION_TYPE_CREDIT_CARD_GENERATION:
            raise ConflictError("Actiunea nu permite alegerea garantiei.")
        if action.status != AgentActionStatus.DRAFT:
            raise ConflictError(f"Actiunea este {action.status.value.lower()} si nu mai poate fi modificata.")
        if _as_aware_utc(action.expires_at) < _now():
            action.status = AgentActionStatus.EXPIRED
            self.repository.flush()
            raise ConflictError("Draftul a expirat. Cere cardul din nou.")

        payload = dict(action.payload)
        amount = Decimal(payload["credit_limit"])
        currency = payload["currency"]
        wallet = self.wallets.get_by_id(wallet_id)
        if (
            wallet is None
            or wallet.user_id != user_id
            or wallet.status != WalletStatus.ACTIVE
            or wallet.currency != currency
            or wallet.available_balance < amount
        ):
            raise ConflictError("Garantia aleasa nu mai este disponibila.")

        option_ids = {str(option["wallet_id"]) for option in payload.get("collateral_options", [])}
        if str(wallet.id) not in option_ids:
            raise ConflictError("Alege una dintre garantiile propuse.")

        payload["collateral_wallet_id"] = str(wallet.id)
        payload["collateral_wallet_label"] = self._collateral_wallet_label(wallet)
        action.payload = payload
        self.repository.flush()
        return self._public(action)

    def select_wallet_currency(
        self,
        user_id: uuid.UUID,
        action_id: uuid.UUID,
        currency_raw: str,
    ) -> AgentActionResultPublic:
        action = self._get_owned(user_id, action_id)
        if action.type != ACTION_TYPE_WALLET_GENERATION:
            raise ConflictError("Actiunea nu permite alegerea monedei.")
        if action.status != AgentActionStatus.DRAFT:
            raise ConflictError(f"Actiunea este {action.status.value.lower()} si nu mai poate fi modificata.")
        if _as_aware_utc(action.expires_at) < _now():
            action.status = AgentActionStatus.EXPIRED
            self.repository.flush()
            raise ConflictError("Draftul a expirat. Cere contul din nou.")

        currency = self._parse_wallet_currency(currency_raw)
        if currency is None:
            raise ConflictError("Alege una dintre monedele propuse.")
        payload = dict(action.payload)
        option_currencies = {option["currency"] for option in payload.get("currency_options", [])}
        if currency not in option_currencies:
            raise ConflictError("Alege una dintre monedele propuse.")
        payload["currency"] = currency
        payload["wallet_label"] = f"{currency} current account"
        action.payload = payload
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

    def _select_source_wallet(self, user_id: uuid.UUID, currency: str, amount: Decimal):
        wallet = self.wallets.get_by_user_and_currency(user_id, currency)
        if wallet is None:
            return f"Nu ai un cont {currency} din care sa fac plata."
        if wallet.status != WalletStatus.ACTIVE:
            return f"Contul tau {currency} este {wallet.status.value.lower()}."
        if wallet.available_balance < amount:
            return f"Sold insuficient: ai {wallet.available_balance} {currency}, iar plata este de {amount} {currency}."
        return wallet

    def _parse_card_tier(self, tier_raw: str | None) -> CardTier | None:
        text = (tier_raw or "REGULAR").strip().upper()
        aliases = {
            "STANDARD": "REGULAR",
            "BASIC": "REGULAR",
            "NORMAL": "REGULAR",
        }
        try:
            return CardTier(aliases.get(text, text))
        except ValueError:
            return None

    def _parse_wallet_currency(self, currency_raw: str | None) -> str | None:
        if currency_raw is None:
            return None
        currency = str(currency_raw).strip().upper()
        if currency in ("LEI", "RON."):
            currency = SUPPORTED_CURRENCY
        return currency if currency in WALLET_CURRENCY_OPTIONS else None

    def _credit_card_collateral_options(self, user_id: uuid.UUID, currency: str, amount: Decimal) -> list[dict]:
        eligible_wallets = [
            wallet
            for wallet in self.wallets.list_for_user(user_id)
            if wallet.status == WalletStatus.ACTIVE
            and wallet.currency == currency
            and wallet.available_balance >= amount
        ]
        debit_cards_by_wallet_id: dict[uuid.UUID, list] = {}
        for card in self.cards.list_for_user(user_id):
            if card.type != CardType.DEBIT or card.status != CardStatus.ACTIVE or card.default_wallet_id is None:
                continue
            debit_cards_by_wallet_id.setdefault(card.default_wallet_id, []).append(card)

        options = []
        for wallet in eligible_wallets:
            options.append(
                {
                    "wallet_id": str(wallet.id),
                    "kind": "current_account",
                    "label": self._collateral_wallet_label(wallet),
                }
            )
            for card in debit_cards_by_wallet_id.get(wallet.id, []):
                options.append(
                    {
                        "wallet_id": str(wallet.id),
                        "kind": "debit_card",
                        "label": f"Debit card **** {card.last_four} - {self._collateral_wallet_label(wallet)}",
                    }
                )
        return options

    def _resolve_credit_card_collateral(
        self,
        user_id: uuid.UUID,
        currency: str,
        amount: Decimal,
        reference: str | None,
    ):
        eligible_wallets = [
            wallet
            for wallet in self.wallets.list_for_user(user_id)
            if wallet.status == WalletStatus.ACTIVE
            and wallet.currency == currency
            and wallet.available_balance >= amount
        ]
        if not eligible_wallets:
            return (
                f"Nu am gasit un cont {currency} care are cel putin {amount:.2f} {currency} "
                "pentru garantia cardului de credit."
            )

        debit_cards_by_wallet_id: dict[uuid.UUID, list] = {}
        for card in self.cards.list_for_user(user_id):
            if card.type != CardType.DEBIT or card.status != CardStatus.ACTIVE or card.default_wallet_id is None:
                continue
            debit_cards_by_wallet_id.setdefault(card.default_wallet_id, []).append(card)

        if reference is None or not str(reference).strip():
            options = []
            for wallet in eligible_wallets:
                options.append(self._collateral_wallet_label(wallet))
                for card in debit_cards_by_wallet_id.get(wallet.id, []):
                    options.append(f"debit card **** {card.last_four} ({self._collateral_wallet_label(wallet)})")
            return "Alege garantia pentru cardul de credit: " + "; ".join(options) + "."

        text = str(reference).strip().lower()
        digits = "".join(ch for ch in text if ch.isdigit())
        matched_wallets = []
        for wallet in eligible_wallets:
            wallet_label = self._collateral_wallet_label(wallet).lower()
            iban_tail = wallet.iban[-4:].lower() if wallet.iban else ""
            if wallet.nickname and wallet.nickname.lower() in text:
                matched_wallets.append(wallet)
                continue
            if wallet_label in text or (iban_tail and iban_tail in text):
                matched_wallets.append(wallet)
                continue
            if wallet.is_main and any(term in text for term in ("main", "principal", "current account", "cont curent")):
                matched_wallets.append(wallet)

        for wallet_id, cards in debit_cards_by_wallet_id.items():
            if all(wallet.id != wallet_id for wallet in eligible_wallets):
                continue
            for card in cards:
                if digits and card.last_four == digits[-4:]:
                    wallet = self.wallets.get_by_id(wallet_id)
                    if wallet is not None:
                        matched_wallets.append(wallet)

        unique_matches = list({wallet.id: wallet for wallet in matched_wallets}.values())
        if len(unique_matches) == 1:
            return unique_matches[0]
        if len(unique_matches) > 1:
            options = "; ".join(self._collateral_wallet_label(wallet) for wallet in unique_matches)
            return f"Am gasit mai multe garantii posibile: {options}. Spune cardul dupa ultimele 4 cifre sau contul exact."
        return "Nu am recunoscut garantia. Spune ultimele 4 cifre ale cardului de debit sau numele/IBAN-ul contului curent."

    def _wallet_label(self, wallet) -> str:
        return f"{wallet.currency} - sold {wallet.available_balance}"

    def _collateral_wallet_label(self, wallet) -> str:
        name = wallet.nickname or ("main account" if wallet.is_main else "current account")
        iban_tail = wallet.iban[-4:] if wallet.iban else "----"
        return f"{name} {wallet.currency} IBAN ****{iban_tail} - available {wallet.available_balance}"

    def _fail(self, action: AgentAction, code: str, detail: str) -> AgentActionResultPublic:
        action.status = AgentActionStatus.FAILED
        action.error_code = code
        action.error_detail = detail[:255]
        self.repository.flush()
        log_event("agent_action_failed", action_id=str(action.id), error_code=code)
        return self._public(action)

    def _card(self, action: AgentAction):
        p = action.payload
        if action.type == ACTION_TYPE_LOAN_PAYMENT:
            return LoanPaymentConfirmCard(
                action_id=action.id,
                title=p["title"],
                amount=p["amount"],
                currency=p["currency"],
                source_wallet_label=p["source_wallet_label"],
                outstanding_principal=p["outstanding_principal"],
                next_payment_date=p.get("next_payment_date"),
                expires_at=action.expires_at,
            )
        if action.type == ACTION_TYPE_CREDIT_CARD_REPAYMENT:
            return CreditCardRepaymentConfirmCard(
                action_id=action.id,
                card_label=p["card_label"],
                amount=p["amount"],
                currency=p["currency"],
                source_wallet_label=p["source_wallet_label"],
                balance_due=p["balance_due"],
                expires_at=action.expires_at,
            )
        if action.type == ACTION_TYPE_CREDIT_CARD_GENERATION:
            return CreditCardGenerationConfirmCard(
                action_id=action.id,
                card_label=p["card_label"],
                tier=p["tier"],
                currency=p["currency"],
                credit_limit=p["credit_limit"],
                collateral_wallet_id=p.get("collateral_wallet_id"),
                collateral_wallet_label=p.get("collateral_wallet_label"),
                collateral_options=p.get("collateral_options", []),
                expires_at=action.expires_at,
            )
        if action.type == ACTION_TYPE_WALLET_GENERATION:
            return WalletGenerationConfirmCard(
                action_id=action.id,
                wallet_label=p["wallet_label"],
                currency=p.get("currency"),
                currency_options=p.get("currency_options", []),
                expires_at=action.expires_at,
            )
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
