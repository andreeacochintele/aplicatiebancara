"""ExportJob — history of generated exports (architecture.md "Exports" table).

Deviates from the documented shape in one way: architecture.md models this as
an async job (PROCESSING -> READY/FAILED, file_path pointing at stored
output), but nothing in this codebase has file-storage or background-job
infrastructure to build that on (same reasoning ExportService's own docstring
already gives for generating synchronously). So generation still happens
synchronously in the request, `status` is always READY the row is written,
and the generated content is stored directly in `content` rather than at a
`file_path` — `file_path` is kept, nullable, for schema fidelity with the
doc and so a real file-storage backend can be dropped in later without a
column rename.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class ExportType(str, enum.Enum):
    STATEMENT = "STATEMENT"
    BUSINESS_TRANSACTIONS = "BUSINESS_TRANSACTIONS"


class ExportFormat(str, enum.Enum):
    CSV = "CSV"
    XLSX = "XLSX"
    PDF = "PDF"


class ExportStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ExportJob(Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type: Mapped[ExportType] = mapped_column(Enum(ExportType, name="export_type"), nullable=False)
    format: Mapped[ExportFormat] = mapped_column(Enum(ExportFormat, name="export_format"), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ExportStatus] = mapped_column(
        Enum(ExportStatus, name="export_status"), nullable=False, default=ExportStatus.READY
    )
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Re-exported so callers building `filters` JSON don't need to import Decimal
# handling themselves — kept here since it's export-specific serialisation,
# not a general JSON concern.
def serialize_filters(**filters: object) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in filters.items() if v is not None}
