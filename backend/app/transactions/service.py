"""Deterministic transaction engine.

architecture.md §44 rule 3: financial operations (balances, ledger, FX rate)
are computed in code, never by an LLM. This is the reference implementation
of internal wallet-to-wallet transfers with paired ledger entries
(architecture.md §7), same-currency or cross-currency via a priced FX quote
(architecture.md §5).

Fraud scoring and multi-step review (PENDING_REVIEW) are out of scope for
Phase 1/2 and are added by the fraud module in a later phase.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.cards.models import CardStatus, CardType
from app.cards.repository import CardRepository
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.fx.service import FXService
from app.merchants.models import MerchantStatus
from app.merchants.repository import MerchantRepository
from app.notifications.service import NotificationsService
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.transactions.schemas import CardPaymentCreate, InternalTransferCreate
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository


class TransactionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = TransactionRepository(db)
        self.wallets = WalletRepository(db)
        self.fx = FXService(db)
        self.cards = CardRepository(db)
        self.merchants = MerchantRepository(db)
        self.notifications = NotificationsService(db)

    def create_internal_transfer(self, initiator_user_id: uuid.UUID, data: InternalTransferCreate) -> Transaction:
        if data.amount <= 0:
            raise ValidationError("Transfer amount must be positive")

        source = self.wallets.get_by_id(data.source_wallet_id)
        destination = self.wallets.get_by_id(data.destination_wallet_id)
        if source is None or destination is None:
            raise NotFoundError("Source or destination wallet not found")
        if source.user_id != initiator_user_id:
            raise ValidationError("Source wallet does not belong to the initiating user")

        if source.currency == destination.currency:
            return self._execute_same_currency_transfer(initiator_user_id, source, destination, data)
        return self._execute_fx_transfer(initiator_user_id, source, destination, data)

    def _execute_same_currency_transfer(
        self, initiator_user_id: uuid.UUID, source: Wallet, destination: Wallet, data: InternalTransferCreate
    ) -> Transaction:
        if source.available_balance < data.amount:
            raise ConflictError("Insufficient available balance")

        transaction = self.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.PROCESSING,
                amount=data.amount,
                currency=source.currency,
                description=data.description,
                processed_at=datetime.now(timezone.utc),
            )
        )
        self._settle(transaction, source, data.amount, destination, data.amount)
        return transaction

    def _execute_fx_transfer(
        self, initiator_user_id: uuid.UUID, source: Wallet, destination: Wallet, data: InternalTransferCreate
    ) -> Transaction:
        if data.fx_quote_id is None:
            raise ValidationError("Cross-currency transfers require an fx_quote_id — request one via POST /fx/quote")

        quote = self.fx.get_valid_quote_for_user(initiator_user_id, data.fx_quote_id)
        if quote.source_currency != source.currency or quote.target_currency != destination.currency:
            raise ValidationError("FX quote currencies don't match the selected wallets")
        if quote.source_amount != data.amount:
            raise ValidationError("Transfer amount doesn't match the quoted source amount")
        if source.available_balance < quote.source_amount:
            raise ConflictError("Insufficient available balance")

        transaction = self.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.PROCESSING,
                amount=quote.target_amount,
                currency=destination.currency,
                source_amount=quote.source_amount,
                source_currency=quote.source_currency,
                exchange_rate=quote.exchange_rate,
                fx_quote_id=quote.id,
                description=data.description,
                processed_at=datetime.now(timezone.utc),
            )
        )
        self._settle(transaction, source, quote.source_amount, destination, quote.target_amount)
        self.fx.mark_accepted(quote)
        return transaction

    def _settle(
        self,
        transaction: Transaction,
        source: Wallet,
        source_amount: Decimal,
        destination: Wallet,
        destination_amount: Decimal,
    ) -> None:
        """Move balances and write the paired ledger entries. Each entry is in
        its own wallet's currency — that's what keeps a cross-currency
        transfer's ledger auditable (architecture.md §7)."""
        source.available_balance -= source_amount
        destination.available_balance += destination_amount

        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=source.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=source_amount,
                currency=source.currency,
                balance_after=source.available_balance,
            )
        )
        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=destination.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=destination_amount,
                currency=destination.currency,
                balance_after=destination.available_balance,
            )
        )

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)
        self.db.flush()

        # Best-effort: a notification failure must never make an otherwise-
        # successful transfer look like it failed.
        try:
            self.notifications.create(
                destination.user_id,
                type="TRANSACTION",
                title="Money received",
                message=f"You received {destination_amount} {destination.currency}.",
                related_transaction_id=transaction.id,
            )
        except Exception:
            pass

    def create_card_payment(self, initiator_user_id: uuid.UUID, data: CardPaymentCreate) -> Transaction:
        """A card payment to a merchant — unlike a transfer, money leaves the
        system to an external counterparty, so only one (DEBIT) ledger entry
        is written, and `merchant_id` is set on the Transaction: it's the
        only signal the rewards module (app/merchants) uses to decide
        whether to credit points, via its own read-only sync — this method
        never calls into rewards/merchants itself."""
        if data.amount <= 0:
            raise ValidationError("Payment amount must be positive")

        card = self.cards.get_by_id(data.card_id)
        if card is None or card.user_id != initiator_user_id:
            raise NotFoundError("Card not found")
        if data.cvv != card.mock_cvv:
            raise ValidationError("Incorrect CVV")
        if card.status != CardStatus.ACTIVE:
            raise ValidationError(f"Card is {card.status.value}, payments require an ACTIVE card")

        merchant = self.merchants.get_by_id(data.merchant_id)
        if merchant is None or merchant.status != MerchantStatus.ACTIVE:
            raise NotFoundError("Merchant not found")

        preferences = self.cards.get_preferences(card.id)
        wallet_id = (preferences.preferred_wallet_id if preferences is not None else None) or card.default_wallet_id
        if wallet_id is None:
            raise ValidationError("Card has no wallet to pay from — set a default or preferred wallet first")

        wallet = self.wallets.get_by_id(wallet_id)
        if wallet is None or wallet.user_id != initiator_user_id:
            raise NotFoundError("Card's wallet not found")
        if wallet.available_balance < data.amount:
            raise ConflictError("Insufficient available balance")

        transaction = self.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=wallet.id,
                merchant_id=merchant.id,
                card_id=card.id,
                type=TransactionType.CARD_PAYMENT,
                status=TransactionStatus.PROCESSING,
                amount=data.amount,
                currency=wallet.currency,
                description=data.description or f"Card payment to {merchant.name}",
                processed_at=datetime.now(timezone.utc),
            )
        )

        wallet.available_balance -= data.amount
        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=data.amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )

        # ONE_TIME cards are meant for exactly one purchase — consuming the
        # single use here (rather than adding a method to app/cards, which
        # isn't this module's) keeps the diff to this one seam.
        if card.type == CardType.ONE_TIME:
            card.one_time_remaining = max(0, (card.one_time_remaining or 1) - 1)
            if card.one_time_remaining == 0:
                card.status = CardStatus.CANCELLED

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return transaction

    def list_for_user(self, user_id: uuid.UUID) -> list[Transaction]:
        return self.repository.list_for_user(user_id)

    def get_for_user(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
        transaction = self.repository.get_for_user(user_id, transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found")
        return transaction
