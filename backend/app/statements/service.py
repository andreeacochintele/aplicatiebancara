"""Statement generation: opening/closing balance, totals and transaction list
for a wallet over a period (architecture.md §24). Read-only report over the
existing ledger — no dedicated table; WalletLedgerEntry.balance_after is the
source of truth for balances (architecture.md §7)."""
import base64
import csv
import io
import uuid
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.exports.models import ExportFormat, ExportJob, ExportType
from app.exports.repository import ExportJobRepository
from app.statements.repository import StatementRepository
from app.statements.schemas import StatementPublic, StatementRequest, StatementTransaction
from app.transactions.models import LedgerEntryType
from app.wallets.repository import WalletRepository


class StatementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = StatementRepository(db)
        self.wallets = WalletRepository(db)
        self.jobs = ExportJobRepository(db)

    def generate(self, user_id: uuid.UUID, data: StatementRequest) -> StatementPublic:
        wallet = self.wallets.get_by_id(data.wallet_id)
        if wallet is None or wallet.user_id != user_id:
            raise NotFoundError("Wallet not found")
        if data.date_from > data.date_to:
            raise ValidationError("date_from must not be after date_to")

        period_start = datetime.combine(data.date_from, time.min, tzinfo=timezone.utc)
        period_end = datetime.combine(data.date_to, time.max, tzinfo=timezone.utc)

        # Opening/closing balance must reflect the wallet's real balance at
        # the period boundaries regardless of the type filter below — a
        # transaction_type filter narrows which activity is *displayed*, it
        # doesn't change what the wallet's balance actually was. Computing
        # closing_balance from a type-filtered entry list picks the wrong
        # "last" entry whenever a different-typed transaction happened after
        # the last matching one in the period.
        all_entries = self.repository.list_entries(wallet.id, period_start, period_end)
        closing_balance = all_entries[-1].balance_after if all_entries else wallet.available_balance
        full_incoming = sum((e.amount for e in all_entries if e.entry_type == LedgerEntryType.CREDIT), Decimal("0"))
        full_outgoing = sum((e.amount for e in all_entries if e.entry_type == LedgerEntryType.DEBIT), Decimal("0"))
        opening_balance = closing_balance - full_incoming + full_outgoing

        entries = (
            [e for e in all_entries if e.transaction.type == data.transaction_type]
            if data.transaction_type is not None
            else all_entries
        )
        total_incoming = sum((e.amount for e in entries if e.entry_type == LedgerEntryType.CREDIT), Decimal("0"))
        total_outgoing = sum((e.amount for e in entries if e.entry_type == LedgerEntryType.DEBIT), Decimal("0"))

        transactions = [
            StatementTransaction(
                id=entry.transaction_id,
                created_at=entry.created_at,
                type=entry.transaction.type,
                status=entry.transaction.status,
                description=entry.transaction.description,
                direction="IN" if entry.entry_type == LedgerEntryType.CREDIT else "OUT",
                amount=entry.amount,
            )
            for entry in entries
            if entry.entry_type in (LedgerEntryType.DEBIT, LedgerEntryType.CREDIT)
        ]

        return StatementPublic(
            wallet_id=wallet.id,
            currency=wallet.currency,
            date_from=data.date_from,
            date_to=data.date_to,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            total_incoming=total_incoming,
            total_outgoing=total_outgoing,
            transactions=transactions,
        )

    def generate_and_log(
        self, user_id: uuid.UUID, data: StatementRequest, file_format: ExportFormat
    ) -> tuple[ExportJob, bytes, str]:
        """Generate the statement, render it, and log an ExportJob row (same
        `exports` table business export uses — architecture.md's ExportType
        has always distinguished STATEMENT from BUSINESS_TRANSACTIONS) so it
        shows up in every user's statement history, not just business
        accounts'."""
        statement = self.generate(user_id, data)
        if file_format == ExportFormat.PDF:
            content = self.to_pdf(statement)
            media_type = "application/pdf"
            extension = "pdf"
            stored_content = base64.b64encode(content).decode("ascii")
        else:
            content = self.to_csv(statement).encode("utf-8")
            media_type = "text/csv"
            extension = "csv"
            stored_content = content.decode("utf-8")

        job = self.jobs.add(
            ExportJob(
                user_id=user_id,
                type=ExportType.STATEMENT,
                format=file_format,
                date_from=data.date_from,
                date_to=data.date_to,
                filters={
                    "wallet_id": str(data.wallet_id),
                    "transaction_type": data.transaction_type.value if data.transaction_type else None,
                },
                row_count=len(statement.transactions),
                content=stored_content,
            )
        )
        self.db.commit()
        filename = f"statement_{statement.currency}_{data.date_from}_{data.date_to}.{extension}"
        return job, content, f"{media_type}|{filename}"

    def list_history(self, user_id: uuid.UUID) -> list[ExportJob]:
        return [job for job in self.jobs.list_for_user(user_id) if job.type == ExportType.STATEMENT]

    def download_job(self, user_id: uuid.UUID, job_id: uuid.UUID) -> tuple[ExportJob, bytes, str]:
        job = self.jobs.get_owned_by_id(user_id, job_id)
        if job is None or job.content is None or job.type != ExportType.STATEMENT:
            raise NotFoundError("Statement export not found")
        extension = job.format.value.lower()
        media_type = "application/pdf" if job.format == ExportFormat.PDF else "text/csv"
        content = base64.b64decode(job.content) if job.format == ExportFormat.PDF else job.content.encode("utf-8")
        filename = f"statement_{job.date_from}_{job.date_to}.{extension}"
        return job, content, f"{media_type}|{filename}"

    @staticmethod
    def to_csv(statement: StatementPublic) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "transaction_id", "type", "status", "direction", "amount", "currency", "description"])
        for tx in statement.transactions:
            writer.writerow(
                [
                    tx.created_at.isoformat(),
                    str(tx.id),
                    tx.type.value,
                    tx.status.value,
                    tx.direction,
                    tx.amount,
                    statement.currency,
                    tx.description or "",
                ]
            )
        return buffer.getvalue()

    @staticmethod
    def to_pdf(statement: StatementPublic) -> bytes:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"Statement - {statement.currency} wallet", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 8, f"Period: {statement.date_from} to {statement.date_to}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Opening balance: {statement.opening_balance} {statement.currency}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Closing balance: {statement.closing_balance} {statement.currency}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Total incoming: {statement.total_incoming} {statement.currency}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Total outgoing: {statement.total_outgoing} {statement.currency}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        col_widths = (28, 30, 22, 25, 65)
        headers = ("Date", "Type", "Direction", "Amount", "Description")
        pdf.set_font("Helvetica", "B", 9)
        for header, width in zip(headers, col_widths):
            pdf.cell(width, 7, header, border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 9)
        for tx in statement.transactions:
            row = (
                tx.created_at.strftime("%Y-%m-%d"),
                tx.type.value,
                tx.direction,
                f"{tx.amount}",
                (tx.description or "")[:40],
            )
            for value, width in zip(row, col_widths):
                pdf.cell(width, 7, value, border=1)
            pdf.ln()

        return bytes(pdf.output())
