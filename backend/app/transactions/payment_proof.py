"""Proof-of-payment document for a single completed transaction.

Deliberately kept out of transactions/service.py: this is a read-only
rendering concern that only one endpoint ever reaches, and service.py is one
of the most frequently edited files in the repo.

Nothing is persisted. The statement exporter logs an ExportJob row, but that
table's `export_type` enum has no value for this document, and adding one
would mean an Alembic migration plus a matching enum change on the shared
Supabase instance — a cost the whole team pays for a document that is cheap
to regenerate on demand.

Reuses core/pdf_branding so this looks like the same bank as the account
statement (same gradient band, palette and footer) instead of a second,
differently-styled letterhead.
"""
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.business.repository import BusinessProfileRepository
from app.core.enums import UserType
from app.core.exceptions import ValidationError
from app.core.pdf_branding import (
    BORDER,
    GREEN,
    RED,
    ROW_ALT,
    TEXT_DARK,
    TEXT_SOFT,
    gradient_color,
    new_branded_pdf,
    pdf_safe_text,
)
from app.merchants.repository import MerchantRepository
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.transactions.service import TransactionService
from app.users.repository import UserRepository
from app.wallets.repository import WalletRepository

_BANK_PARTY_NAME = "EasyB"
_UNKNOWN_ACCOUNT = "-"
_UNKNOWN_PARTY_NAME = "Not recorded"

# Types whose other side genuinely is the bank itself, so naming it "EasyB" is
# accurate rather than a guess: cashback paid out, a loan instalment collected,
# a top-up credited, money moved in or out of a savings goal. Every other type
# has a real counterparty, and if we cannot resolve it we say so instead of
# printing "EasyB" on a document that is meant to prove who was paid.
_BANK_COUNTERPARTY_TYPES = frozenset(
    {
        TransactionType.CASHBACK,
        TransactionType.LOAN_PAYMENT,
        TransactionType.TOP_UP,
        TransactionType.SAVINGS_CONTRIBUTION,
        TransactionType.SAVINGS_WITHDRAWAL,
    }
)

# An off-us transfer stores no destination wallet and no counterparty user —
# payments/service.py records the beneficiary only inside the generated
# description, as "Transfer to <name> - <account>", with " (BIC: <bic>)"
# appended when the account is not an IBAN. Parsing it back is the only way to
# name the payee on the confirmation. Best-effort by design: a transfer the
# user gave their own description to will not match, and then the payee is
# reported as unknown rather than guessed at.
_TRANSFER_DESCRIPTION = re.compile(
    r"^Transfer to (?P<name>.+?) - (?P<account>[A-Z0-9]{6,34})"
    r"(?: \(BIC: (?P<bic>[A-Z0-9]{8,11})\))?$"
)


@dataclass(frozen=True)
class _Party:
    name: str
    account: str


class PaymentProofService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.transactions = TransactionService(db)
        self.wallets = WalletRepository(db)
        self.users = UserRepository(db)
        self.merchants = MerchantRepository(db)
        self.business_profiles = BusinessProfileRepository(db)

    def generate(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> tuple[bytes, str]:
        """Returns (pdf_bytes, filename). Ownership is enforced by
        TransactionService.get_for_user, which 404s a transaction belonging
        to someone else — a confirmation names both parties, so it must never
        be reachable for a transaction the caller was not part of."""
        transaction = self.transactions.get_for_user(user_id, transaction_id)
        if transaction.status != TransactionStatus.COMPLETED:
            # A document headed "confirmation" must not exist for money that
            # has not actually moved.
            raise ValidationError("Only completed transactions have a payment confirmation")

        content = self._render(user_id, transaction)
        return content, f"payment_proof_{str(transaction.id)[:8]}.pdf"

    # ---- party resolution -------------------------------------------------

    def _holder_name(self, user_id: uuid.UUID | None) -> str:
        """The name this account trades under: the company for a business
        user, the person's own name otherwise. Mirrors how the account
        statement picks its account-holder line."""
        if user_id is None:
            return _BANK_PARTY_NAME
        user = self.users.get_by_id(user_id)
        if user is None:
            return _UNKNOWN_ACCOUNT
        if user.user_type == UserType.BUSINESS:
            profile = next((p for p in self.business_profiles.list_for_user(user_id) if p.is_active), None)
            if profile is not None:
                return profile.company_name
        return f"{user.first_name} {user.last_name}".strip() or _UNKNOWN_ACCOUNT

    def _wallet_party(self, wallet_id: uuid.UUID | None) -> _Party | None:
        if wallet_id is None:
            return None
        wallet = self.wallets.get_by_id(wallet_id)
        if wallet is None:
            return None
        return _Party(name=self._holder_name(wallet.user_id), account=wallet.iban)

    def _merchant_party(self, transaction: Transaction) -> _Party | None:
        if transaction.merchant_id is None:
            return None
        merchant = self.merchants.get_by_id(transaction.merchant_id)
        if merchant is None:
            return None
        return _Party(name=merchant.name, account=_UNKNOWN_ACCOUNT)

    def _counterparty_user_party(self, transaction: Transaction) -> _Party | None:
        if transaction.counterparty_user_id is None:
            return None
        return _Party(name=self._holder_name(transaction.counterparty_user_id), account=_UNKNOWN_ACCOUNT)

    @staticmethod
    def _described_party(transaction: Transaction) -> _Party | None:
        match = _TRANSFER_DESCRIPTION.match(transaction.description or "")
        if match is None:
            return None
        return _Party(name=match.group("name"), account=match.group("account"))

    @staticmethod
    def _fallback_party(transaction: Transaction) -> _Party:
        if transaction.type in _BANK_COUNTERPARTY_TYPES:
            return _Party(_BANK_PARTY_NAME, _UNKNOWN_ACCOUNT)
        return _Party(_UNKNOWN_PARTY_NAME, _UNKNOWN_ACCOUNT)

    def _parties(self, transaction: Transaction) -> tuple[_Party, _Party]:
        payer = self._wallet_party(transaction.source_wallet_id) or self._fallback_party(transaction)
        payee = (
            self._wallet_party(transaction.destination_wallet_id)
            or self._merchant_party(transaction)
            or self._counterparty_user_party(transaction)
            # Only for the payee: the description records where money went,
            # never where it came from.
            or self._described_party(transaction)
            or self._fallback_party(transaction)
        )
        return payer, payee

    def _heading(self, user_id: uuid.UUID, transaction: Transaction) -> tuple[str, tuple[int, int, int], str]:
        """(title, amount colour, signed-amount prefix) from the requesting
        user's point of view — the same transaction is a payment sent to one
        side and a payment received on the other."""
        own_wallet_ids = {wallet.id for wallet in self.wallets.list_for_user(user_id)}
        sent = transaction.source_wallet_id in own_wallet_ids
        received = transaction.destination_wallet_id in own_wallet_ids
        if sent and received:
            return "Transfer between your own accounts", TEXT_DARK, ""
        if received:
            return "Payment received", GREEN, "+"
        return "Payment sent", RED, "-"

    # ---- rendering --------------------------------------------------------

    def _render(self, user_id: uuid.UUID, transaction: Transaction) -> bytes:
        title, amount_color, sign = self._heading(user_id, transaction)
        payer, payee = self._parties(transaction)

        pdf = new_branded_pdf(subtitle="Payment Confirmation")
        pdf.footer_note = "sandbox confirmation, not a legal document"
        content_w = pdf.w - 20

        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*TEXT_DARK)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        # The amount is the one thing anyone reading this document is looking
        # for, so it gets its own banner rather than a row in the table.
        x0, y0 = pdf.get_x(), pdf.get_y()
        pdf.set_draw_color(*BORDER)
        pdf.set_fill_color(*ROW_ALT)
        pdf.rect(x0, y0, content_w, 22, style="FD")
        pdf.set_xy(x0 + 4, y0 + 3)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*TEXT_SOFT)
        pdf.cell(content_w - 8, 4, "AMOUNT")
        pdf.set_xy(x0 + 4, y0 + 9)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*amount_color)
        pdf.cell(content_w - 8, 9, f"{sign}{transaction.amount} {transaction.currency}")
        pdf.set_xy(x0, y0 + 28)

        self._party_boxes(pdf, content_w, payer, payee)
        self._detail_rows(pdf, content_w, transaction)
        return bytes(pdf.output())

    @staticmethod
    def _party_boxes(pdf, content_w: float, payer: _Party, payee: _Party) -> None:
        box_w = content_w / 2
        box_h = 24
        x0, y0 = pdf.get_x(), pdf.get_y()
        for i, (label, party) in enumerate((("FROM", payer), ("TO", payee))):
            x = x0 + i * box_w
            pdf.set_draw_color(*BORDER)
            pdf.rect(x, y0, box_w - 3, box_h, style="D")
            pdf.set_xy(x + 3, y0 + 2.5)
            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_text_color(*TEXT_SOFT)
            pdf.cell(box_w - 9, 4, label)
            pdf.set_xy(x + 3, y0 + 8)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*TEXT_DARK)
            pdf.cell(box_w - 9, 5, pdf_safe_text(party.name)[:34])
            pdf.set_xy(x + 3, y0 + 14.5)
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*TEXT_SOFT)
            pdf.cell(box_w - 9, 5, party.account)
        pdf.set_xy(x0, y0 + box_h + 8)

    @staticmethod
    def _detail_rows(pdf, content_w: float, transaction: Transaction) -> None:
        rows: list[tuple[str, str]] = [
            ("Reference", str(transaction.id)),
            ("Date", transaction.created_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("Type", transaction.type.value.replace("_", " ").title()),
            ("Status", transaction.status.value.title()),
        ]
        if transaction.completed_at is not None:
            rows.append(("Completed", transaction.completed_at.strftime("%Y-%m-%d %H:%M UTC")))
        # An FX conversion debits one currency and credits another; showing
        # only `amount` would document half of what happened.
        if transaction.source_amount is not None and transaction.source_currency is not None:
            rows.append(("Charged", f"{transaction.source_amount} {transaction.source_currency}"))
        if transaction.exchange_rate is not None:
            rate = transaction.exchange_rate
            # Numeric(18, 8) serialises as "4.97600000"; normalize() trims the
            # trailing zeros the column pads it with.
            rows.append(("Exchange rate", str(rate.normalize() if isinstance(rate, Decimal) else rate)))
        if transaction.description:
            rows.append(("Details", pdf_safe_text(transaction.description)))

        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(*gradient_color(0.15))
        pdf.set_text_color(255, 255, 255)
        pdf.cell(content_w, 8, "  Transaction details", border=0, fill=True, new_x="LMARGIN", new_y="NEXT")

        label_w = 40
        for i, (label, value) in enumerate(rows):
            pdf.set_fill_color(*(ROW_ALT if i % 2 else (255, 255, 255)))
            pdf.set_draw_color(*BORDER)
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*TEXT_SOFT)
            pdf.cell(label_w, 7, f"  {label}", border="B", fill=True)
            pdf.set_text_color(*TEXT_DARK)
            # multi_cell so a 500-character description wraps instead of
            # spilling off the page edge.
            x_after, y_before = pdf.get_x(), pdf.get_y()
            pdf.multi_cell(content_w - label_w, 7, value, border="B", fill=True, new_x="LMARGIN", new_y="NEXT")
            if pdf.get_y() == y_before:  # pragma: no cover - defensive
                pdf.set_xy(x_after, y_before + 7)
