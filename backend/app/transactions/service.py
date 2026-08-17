"""Deterministic transaction engine.

architecture.md §44 rule 3: financial operations (balances, ledger) are
computed in code, never by an LLM. This is the reference implementation of
the simplest end-to-end flow: an internal, same-currency wallet-to-wallet
transfer with paired ledger entries (architecture.md §7).

Fraud scoring, FX conversion and multi-step review (PENDING_REVIEW) are out
of scope for Phase 1 and are added by the fraud/fx modules in later phases.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.transactions.schemas import InternalTransferCreate
from app.wallets.repository import WalletRepository


class TransactionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = TransactionRepository(db)
        self.wallets = WalletRepository(db)

    def create_internal_transfer(self, initiator_user_id: uuid.UUID, data: InternalTransferCreate) -> Transaction:
        if data.amount <= 0:
            raise ValidationError("Transfer amount must be positive")

        source = self.wallets.get_by_id(data.source_wallet_id)
        destination = self.wallets.get_by_id(data.destination_wallet_id)
        if source is None or destination is None:
            raise NotFoundError("Source or destination wallet not found")
        if source.user_id != initiator_user_id:
            raise ValidationError("Source wallet does not belong to the initiating user")
        if source.currency != destination.currency:
            raise ValidationError("Cross-currency transfers require an FX quote (not implemented in Phase 1)")
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

        source.available_balance -= data.amount
        destination.available_balance += data.amount

        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=source.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=data.amount,
                currency=source.currency,
                balance_after=source.available_balance,
            )
        )
        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=destination.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=data.amount,
                currency=destination.currency,
                balance_after=destination.available_balance,
            )
        )

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return transaction

    def list_for_user(self, user_id: uuid.UUID) -> list[Transaction]:
        return self.repository.list_for_user(user_id)

    def get_for_user(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
        transaction = self.repository.get_by_id(transaction_id)
        if transaction is None or transaction.initiator_user_id != user_id:
            raise NotFoundError("Transaction not found")
        return transaction
