"""Business transaction export (architecture.md §25): a filtered CSV/XLSX of a
business user's own transaction activity, generated synchronously and
in-memory — same shape as statements/service.py's to_csv, no dedicated
export/job table for the *generation* step. See the QA punch-list report for
why this follows the statements precedent rather than architecture.md's
documented async exports-table model: nothing else in this codebase has
file-storage/background job infrastructure to build on, and "Format inițial:
CSV" (architecture.md §25) doesn't need it.

Each generated export is still logged to the `exports` table (ExportJob) so a
user can see and re-download past exports — see exports/models.py for how
that deviates from the doc's async-job shape."""
import base64
import csv
import io
import uuid
from datetime import datetime, time, timezone
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.exports.models import ExportFormat, ExportJob, ExportType
from app.exports.repository import ExportJobRepository, ExportRepository
from app.exports.schemas import (
    ExportCurrencyTotal,
    ExportedTransaction,
    ExportJobPublic,
    TransactionExportPreview,
    TransactionExportRequest,
)
from app.merchants.repository import MerchantRepository
from app.transactions.models import LedgerEntryType
from app.users.repository import UserRepository
from app.wallets.repository import WalletRepository

_CSV_COLUMNS = ["date", "transaction_id", "type", "counterparty", "description", "category", "amount", "currency", "status"]

# Both the rendered file and the row-level preview are built fully in memory
# and (via generate_and_log) stored inline as a single DB column — unbounded
# like this, a business account with a long history could pull its entire
# transaction lifetime into one request/row. Capping the date range (like
# fx/service.py's rate-history endpoint caps `days`) is a first line of
# defense; row-count pagination would be the next step if this module ever
# grows past on-demand CSV/XLSX generation.
_MAX_EXPORT_RANGE_DAYS = 366


class ExportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ExportRepository(db)
        self.jobs = ExportJobRepository(db)
        self.wallets = WalletRepository(db)
        self.users = UserRepository(db)
        self.merchants = MerchantRepository(db)

    def build_preview(self, user_id: uuid.UUID, data: TransactionExportRequest) -> TransactionExportPreview:
        if data.date_from > data.date_to:
            raise ValidationError("date_from must not be after date_to")
        if (data.date_to - data.date_from).days > _MAX_EXPORT_RANGE_DAYS:
            raise ValidationError(f"Date range too large — export at most {_MAX_EXPORT_RANGE_DAYS} days at a time")
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

        category_ids = {e.transaction.category_id for e in entries if e.transaction.category_id is not None}
        category_names = self.repository.get_category_names(category_ids)

        counterparty_cache: dict[tuple[str, uuid.UUID], str] = {}
        transactions = [
            ExportedTransaction(
                date=entry.created_at,
                transaction_id=entry.transaction_id,
                type=entry.transaction.type,
                counterparty=self._resolve_counterparty(entry.transaction, counterparty_cache),
                description=entry.transaction.description,
                category=category_names.get(entry.transaction.category_id),
                amount=entry.amount,
                currency=entry.currency,
                status=entry.transaction.status,
            )
            for entry in entries
        ]

        totals: dict[str, dict[str, Decimal]] = {}
        for entry in entries:
            bucket = totals.setdefault(entry.currency, {"in": Decimal("0"), "out": Decimal("0")})
            if entry.entry_type == LedgerEntryType.CREDIT:
                bucket["in"] += entry.amount
            elif entry.entry_type == LedgerEntryType.DEBIT:
                bucket["out"] += entry.amount

        return TransactionExportPreview(
            date_from=data.date_from,
            date_to=data.date_to,
            row_count=len(transactions),
            totals=[
                ExportCurrencyTotal(currency=currency, total_incoming=v["in"], total_outgoing=v["out"])
                for currency, v in sorted(totals.items())
            ],
            transactions=transactions,
        )

    def generate_and_log(
        self, user_id: uuid.UUID, data: TransactionExportRequest, file_format: ExportFormat
    ) -> tuple[ExportJob, bytes, str]:
        """Build the preview, render it to the requested format, and log an
        ExportJob row so it shows up in export history — used by both the
        direct-download route and (later) any route that just wants the
        history entry."""
        preview = self.build_preview(user_id, data)
        if file_format == ExportFormat.XLSX:
            content = self.to_xlsx(preview)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            extension = "xlsx"
            stored_content = base64.b64encode(content).decode("ascii")
        else:
            content = self.to_csv(preview).encode("utf-8")
            media_type = "text/csv"
            extension = "csv"
            stored_content = content.decode("utf-8")

        job = self.jobs.add(
            ExportJob(
                user_id=user_id,
                type=ExportType.BUSINESS_TRANSACTIONS,
                format=file_format,
                date_from=data.date_from,
                date_to=data.date_to,
                filters={
                    k: (str(v) if not isinstance(v, str) else v)
                    for k, v in data.model_dump(exclude={"date_from", "date_to"}).items()
                    if v is not None
                },
                row_count=preview.row_count,
                content=stored_content,
            )
        )
        self.db.commit()
        filename = f"transactions_{data.date_from}_{data.date_to}.{extension}"
        return job, content, f"{media_type}|{filename}"

    def list_history(self, user_id: uuid.UUID) -> list[ExportJobPublic]:
        return [ExportJobPublic.model_validate(job, from_attributes=True) for job in self.jobs.list_for_user(user_id)]

    def download_job(self, user_id: uuid.UUID, job_id: uuid.UUID) -> tuple[ExportJob, bytes, str]:
        job = self.jobs.get_owned_by_id(user_id, job_id)
        if job is None or job.content is None:
            raise NotFoundError("Export not found")
        extension = job.format.value.lower()
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if job.format == ExportFormat.XLSX
            else "text/csv"
        )
        content = base64.b64decode(job.content) if job.format == ExportFormat.XLSX else job.content.encode("utf-8")
        filename = f"transactions_{job.date_from}_{job.date_to}.{extension}"
        return job, content, f"{media_type}|{filename}"

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
    def to_csv(preview: TransactionExportPreview) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_CSV_COLUMNS)
        for tx in preview.transactions:
            writer.writerow(
                [
                    tx.date.isoformat(),
                    str(tx.transaction_id),
                    tx.type.value,
                    tx.counterparty,
                    tx.description or "",
                    tx.category or "",
                    tx.amount,
                    tx.currency,
                    tx.status.value,
                ]
            )
        if preview.totals:
            writer.writerow([])
            writer.writerow(["TOTALS", "currency", "incoming", "outgoing"])
            for total in preview.totals:
                writer.writerow(["", total.currency, total.total_incoming, total.total_outgoing])
        return buffer.getvalue()

    @staticmethod
    def to_xlsx(preview: TransactionExportPreview) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Transactions"
        sheet.append(_CSV_COLUMNS)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for tx in preview.transactions:
            sheet.append(
                [
                    tx.date.replace(tzinfo=None),
                    str(tx.transaction_id),
                    tx.type.value,
                    tx.counterparty,
                    tx.description or "",
                    tx.category or "",
                    float(tx.amount),
                    tx.currency,
                    tx.status.value,
                ]
            )
        for index, column in enumerate(_CSV_COLUMNS, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = max(12, len(column) + 2)

        if preview.totals:
            totals_sheet = workbook.create_sheet("Totals")
            totals_sheet.append(["currency", "incoming", "outgoing"])
            for cell in totals_sheet[1]:
                cell.font = Font(bold=True)
            for total in preview.totals:
                totals_sheet.append([total.currency, float(total.total_incoming), float(total.total_outgoing)])

        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()
