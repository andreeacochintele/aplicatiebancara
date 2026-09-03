"""Add business profile KYB verification: business_profiles gets a
verification_status (PENDING_VERIFICATION/VERIFIED/REJECTED) plus who/when
decided it, and a new business_documents table holds the proof-of-company
uploads (registration certificate, articles of association, legal
representative ID, optional proof of address) an admin reviews - same
"engine flags, admin decides" shape as fraud/credit, and the same
base64-column document shape as credit_documents.

Revision ID: 0058_business_verification
Revises: 0057_merge_heads
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058_business_verification"
down_revision: Union[str, None] = "0057_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    verification_status = postgresql.ENUM(
        "PENDING_VERIFICATION", "VERIFIED", "REJECTED", name="business_verification_status"
    )
    document_type = postgresql.ENUM(
        "REGISTRATION_CERTIFICATE",
        "ARTICLES_OF_ASSOCIATION",
        "LEGAL_REPRESENTATIVE_ID",
        "PROOF_OF_ADDRESS",
        name="business_document_type",
    )
    document_status = postgresql.ENUM("UPLOADED", "APPROVED", "REJECTED", name="business_document_status")
    verification_status.create(op.get_bind(), checkfirst=True)
    document_type.create(op.get_bind(), checkfirst=True)
    document_status.create(op.get_bind(), checkfirst=True)
    verification_status = postgresql.ENUM(
        "PENDING_VERIFICATION", "VERIFIED", "REJECTED", name="business_verification_status", create_type=False
    )
    document_type = postgresql.ENUM(
        "REGISTRATION_CERTIFICATE",
        "ARTICLES_OF_ASSOCIATION",
        "LEGAL_REPRESENTATIVE_ID",
        "PROOF_OF_ADDRESS",
        name="business_document_type",
        create_type=False,
    )
    document_status = postgresql.ENUM(
        "UPLOADED", "APPROVED", "REJECTED", name="business_document_status", create_type=False
    )

    op.add_column(
        "business_profiles",
        sa.Column(
            "verification_status", verification_status, nullable=False, server_default="PENDING_VERIFICATION"
        ),
    )
    op.add_column("business_profiles", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "business_profiles",
        sa.Column("verified_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("business_profiles", sa.Column("rejection_reason", sa.String(length=500), nullable=True))

    op.create_table(
        "business_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_profiles.id"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_type", document_type, nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_base64", sa.Text(), nullable=True),
        sa.Column("status", document_status, nullable=False, server_default="UPLOADED"),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_business_documents_business_profile_id", "business_documents", ["business_profile_id"])
    op.create_index("ix_business_documents_user_id", "business_documents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_business_documents_user_id", table_name="business_documents")
    op.drop_index("ix_business_documents_business_profile_id", table_name="business_documents")
    op.drop_table("business_documents")
    op.drop_column("business_profiles", "rejection_reason")
    op.drop_column("business_profiles", "verified_by_admin_id")
    op.drop_column("business_profiles", "verified_at")
    op.drop_column("business_profiles", "verification_status")
    postgresql.ENUM(name="business_document_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="business_document_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="business_verification_status").drop(op.get_bind(), checkfirst=True)
