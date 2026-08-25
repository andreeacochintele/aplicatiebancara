"""Add credit document review metadata.

Revision ID: 0031_credit_documents
Revises: 0030_credit_currency_dates
Create Date: 2026-08-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_credit_documents"
down_revision: Union[str, None] = "0030_credit_currency_dates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    document_purpose = postgresql.ENUM("CREDIT_SCORE", "LOAN_APPLICATION", name="credit_document_purpose")
    document_status = postgresql.ENUM(
        "UPLOADED",
        "APPROVED",
        "REJECTED",
        "NEEDS_MORE_INFO",
        name="credit_document_status",
    )
    document_purpose.create(op.get_bind(), checkfirst=True)
    document_status.create(op.get_bind(), checkfirst=True)
    document_purpose = postgresql.ENUM("CREDIT_SCORE", "LOAN_APPLICATION", name="credit_document_purpose", create_type=False)
    document_status = postgresql.ENUM(
        "UPLOADED",
        "APPROVED",
        "REJECTED",
        "NEEDS_MORE_INFO",
        name="credit_document_status",
        create_type=False,
    )

    op.create_table(
        "credit_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_applications.id"),
            nullable=True,
        ),
        sa.Column("purpose", document_purpose, nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", document_status, nullable=False, server_default="UPLOADED"),
        sa.Column("evaluation_score", sa.Integer(), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_credit_documents_user_id", "credit_documents", ["user_id"])
    op.create_index("ix_credit_documents_application_id", "credit_documents", ["application_id"])
    op.create_index("ix_credit_documents_status", "credit_documents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_credit_documents_status", table_name="credit_documents")
    op.drop_index("ix_credit_documents_application_id", table_name="credit_documents")
    op.drop_index("ix_credit_documents_user_id", table_name="credit_documents")
    op.drop_table("credit_documents")
    postgresql.ENUM(name="credit_document_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="credit_document_purpose").drop(op.get_bind(), checkfirst=True)
