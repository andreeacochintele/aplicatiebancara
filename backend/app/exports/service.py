"""Business transaction export (architecture.md §25): a filtered CSV of a
business user's own transaction activity, generated synchronously and
in-memory — same shape as statements/service.py's to_csv, no dedicated
export/job table. See the QA punch-list report for why this follows the
statements precedent rather than architecture.md's documented async
exports-table model: nothing else in this codebase has file-storage/background
job infrastructure to build on, and "Format inițial: CSV" (architecture.md
§25) doesn't need it."""
import csv
import io
import uuid
from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.exports.repository import ExportRepository
from app.exports.schemas import ExportedTransaction, TransactionExportRequest
from app.merchants.repository import MerchantRepository
from app.users.repository import UserRepository
from app.wallets.repository import WalletRepository


class ExportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ExportRepository(db)
        self.wallets = WalletRepository(db)
        self.users = UserRepository(db)
        self.merchants = MerchantRepository(db)

    def list_transactions(self, user_id: uuid.UUID, data: TransactionExportRequest) -> list[ExportedTransaction]:
        if data.date_from > data.date_to:
            raise ValidationError("date_from must not be after date_to")
        if data.wallet_id is not None:
            wallet = self.wallets.get_by_id(data.wallet_id)
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Wallet not found")

        period_start = datetime.combine(data.date_from, time.min, tzinfo=timezone.utc)
        period_end = datetime.combine(data.date_to, time.max, tzinfo=timezone.utc)

        entries = self.repository.list_entries_for_user(
            user_id,
            period_start,
            period_end,
            wallet_id=data.wallet_id,
            currency=data.currency,
            direction=data.direction,
            status=data.status,
            category_id=data.category_id,
        )

        counterparty_cache: dict[tuple[str, uuid.UUID], str] = {}
        return [
            ExportedTransaction(
                date=entry.created_at,
                transaction_id=entry.transaction_id,
                type=entry.transaction.type,
                counterparty=self._resolve_counterparty(entry.transaction, counterparty_cache),
                description=entry.transaction.description,
                amount=entry.amount,
                currency=entry.currency,
                status=entry.transaction.status,
            )
            for entry in entries
        ]

    def _resolve_counterparty(self, transaction, cache: dict[tuple[str, uuid.UUID], str]) -> str:
        if transaction.merchant_id is not None:
            key = ("merchant", transaction.merchant_id)
            if key not in cache:
                merchant = self.merchants.get_by_id(transaction.merchant_id)
                cache[key] = merchant.name if merchant is not None else ""
            return cache[key]
        if transaction.counterparty_user_id is not None:
            key = ("user", transaction.counterparty_user_id)
            if key not in cache:
                counterparty = self.users.get_by_id(transaction.counterparty_user_id)
                cache[key] = f"{counterparty.first_name} {counterparty.last_name}" if counterparty is not None else ""
            return cache[key]
        return ""

    @staticmethod
    def to_csv(transactions: list[ExportedTransaction]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["date", "transaction_id", "type", "counterparty", "description", "amount", "currency", "status"]
        )
        for tx in transactions:
            writer.writerow(
                [
                    tx.date.isoformat(),
                    str(tx.transaction_id),
                    tx.type.value,
                    tx.counterparty,
                    tx.description or "",
                    tx.amount,
                    tx.currency,
                    tx.status.value,
                ]
            )
        return buffer.getvalue()
