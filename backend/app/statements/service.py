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

from app.business.repository import BusinessProfileRepository
from app.core.enums import UserType
from app.core.exceptions import NotFoundError, ValidationError
from app.exports.models import ExportFormat, ExportJob, ExportType
from app.exports.repository import ExportJobRepository
from app.statements.repository import StatementRepository
from app.statements.schemas import StatementPublic, StatementRequest, StatementTransaction
from app.transactions.models import LedgerEntryType
from app.users.repository import UserRepository
from app.wallets.repository import WalletRepository


class StatementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = StatementRepository(db)
        self.wallets = WalletRepository(db)
        self.users = UserRepository(db)
        self.business_profiles = BusinessProfileRepository(db)
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

        holder = self.users.get_by_id(user_id)
        holder_name = f"{holder.first_name} {holder.last_name}".strip() if holder is not None else ""
        representative_name = None
        if holder is not None and holder.user_type == UserType.BUSINESS:
            active_profile = next((p for p in self.business_profiles.list_for_user(user_id) if p.is_active), None)
            if active_profile is not None:
                holder_name = active_profile.company_name
                representative_name = active_profile.representative_name

        return StatementPublic(
            wallet_id=wallet.id,
            iban=wallet.iban,
            account_holder_name=holder_name,
            representative_name=representative_name,
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
        from app.core.pdf_branding import BORDER, GREEN, RED, ROW_ALT, TEXT_DARK, TEXT_SOFT, gradient_color, new_branded_pdf, pdf_safe_text

        _TEXT_DARK, _TEXT_SOFT, _BORDER, _ROW_ALT, _GREEN, _RED = TEXT_DARK, TEXT_SOFT, BORDER, ROW_ALT, GREEN, RED
        _gradient_color = gradient_color

        pdf = new_branded_pdf(subtitle="Account Statement")
        pdf.footer_note = "sandbox statement, not a legal document"

        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*_TEXT_DARK)
        pdf.cell(0, 8, f"{statement.currency} wallet statement", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*_TEXT_SOFT)
        label_w = 32
        detail_lines = [
            ("Account holder", pdf_safe_text(statement.account_holder_name) or "-"),
            *(
                [("Representative", pdf_safe_text(statement.representative_name))]
                if statement.representative_name
                else []
            ),
            ("IBAN", statement.iban),
            ("Period", f"{statement.date_from} to {statement.date_to}"),
        ]
        for label, value in detail_lines:
            pdf.set_text_color(*_TEXT_SOFT)
            pdf.cell(label_w, 6, label)
            pdf.set_text_color(*_TEXT_DARK)
            pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        stats = (
            ("Opening balance", statement.opening_balance, _TEXT_DARK),
            ("Closing balance", statement.closing_balance, _TEXT_DARK),
            ("Total incoming", statement.total_incoming, _GREEN),
            ("Total outgoing", statement.total_outgoing, _RED),
        )
        box_w = (pdf.w - 20) / 4
        box_h = 18
        x0, y0 = pdf.get_x(), pdf.get_y()
        for i, (label, value, color) in enumerate(stats):
            x = x0 + i * box_w
            pdf.set_draw_color(*_BORDER)
            pdf.set_fill_color(*_ROW_ALT)
            pdf.rect(x, y0, box_w - 3, box_h, style="FD")
            pdf.set_xy(x + 2, y0 + 2.5)
            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_text_color(*_TEXT_SOFT)
            pdf.cell(box_w - 6, 4, label.upper())
            pdf.set_xy(x + 2, y0 + 8.5)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(*color)
            pdf.cell(box_w - 6, 6, f"{value} {statement.currency}")
        pdf.set_xy(x0, y0 + box_h + 6)
        pdf.set_text_color(*_TEXT_DARK)

        col_widths = (22, 18, 30, 16, 26, 58)
        headers = ("Date", "Tx ID", "Type", "Direction", "Amount", "Description")
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(*_gradient_color(0.15))
        pdf.set_text_color(255, 255, 255)
        for header, width in zip(headers, col_widths):
            pdf.cell(width, 8, header, border=0, fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8.5)
        if not statement.transactions:
            pdf.set_text_color(*_TEXT_SOFT)
            pdf.cell(sum(col_widths), 10, "No transactions in this period.", border="LRB")
            pdf.ln()
        for i, tx in enumerate(statement.transactions):
            pdf.set_fill_color(*(_ROW_ALT if i % 2 else (255, 255, 255)))
            pdf.set_draw_color(*_BORDER)
            row = (
                tx.created_at.strftime("%Y-%m-%d"),
                str(tx.id)[:8],
                tx.type.value.replace("_", " ").title(),
                tx.direction,
                f"{'+' if tx.direction == 'IN' else '-'}{tx.amount}",
                pdf_safe_text(tx.description)[:36],
            )
            pdf.set_text_color(*_TEXT_DARK)
            for col, (value, width) in enumerate(zip(row, col_widths)):
                if col == 4:
                    pdf.set_text_color(*(_GREEN if tx.direction == "IN" else _RED))
                pdf.cell(width, 7, value, border="B", fill=True)
                if col == 4:
                    pdf.set_text_color(*_TEXT_DARK)
            pdf.ln()

        return bytes(pdf.output())
