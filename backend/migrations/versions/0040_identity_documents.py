"""Onboarding step 3: identity document upload, MRZ extraction and review.

Adds VERIFIED / NEEDS_REVIEW / APPROVED / REJECTED to kyc_document_status
(NOT_STARTED and the now-unused legacy PLACEHOLDER are kept as-is) and a new
identity_documents table (front/back images, MRZ-extracted fields, and the
admin-review fields), mirroring credit_documents' upload+review shape.

NOTE ON ALEMBIC HEADS: this branches off 0039_ai_insights_currency, the
newest of three heads that already existed on master before this branch was
created (0036_card_pin_hash and 0037_wallet_iban are the other two - neither
had been merged back into the main line yet). This migration does not
attempt to reconcile that pre-existing split; a separate merge migration
will still be needed regardless of this feature, and should be handled by
whoever owns those two branches rather than folded in here.

Revision ID: 0040_identity_documents
Revises: 0039_ai_insights_currency
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_identity_documents"
down_revision: Union[str, None] = "0039_ai_insights_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_KYC_STATUS_VALUES = ("VERIFIED", "NEEDS_REVIEW", "APPROVED", "REJECTED")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in _NEW_KYC_STATUS_VALUES:
            op.execute(f"ALTER TYPE kyc_document_status ADD VALUE IF NOT EXISTS '{value}'")

    mrz_format_code = postgresql.ENUM("TD1", "TD2", name="mrz_format_code")
    mrz_format_code.create(bind, checkfirst=True)

    kyc_document_status = postgresql.ENUM(
        "NOT_STARTED",
        "PLACEHOLDER",
        *_NEW_KYC_STATUS_VALUES,
        name="kyc_document_status",
        create_type=False,
    )

    op.create_table(
        "identity_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("front_image_base64", sa.Text(), nullable=True),
        sa.Column("back_image_base64", sa.Text(), nullable=True),
        sa.Column("detected_format", mrz_format_code, nullable=True),
        sa.Column("extracted_surname", sa.String(length=100), nullable=True),
        sa.Column("extracted_given_names", sa.String(length=100), nullable=True),
        sa.Column("extracted_cnp", sa.String(length=13), nullable=True),
        sa.Column("extracted_date_of_birth", sa.Date(), nullable=True),
        sa.Column("extracted_date_of_expiry", sa.Date(), nullable=True),
        sa.Column("mrz_checks_passed", sa.Boolean(), nullable=False),
        sa.Column("cross_check_passed", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("status", kyc_document_status, nullable=False),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_admin_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_identity_documents_user_id"), "identity_documents", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_identity_documents_user_id"), table_name="identity_documents")
    op.drop_table("identity_documents")
    postgresql.ENUM(name="mrz_format_code").drop(op.get_bind(), checkfirst=True)
    # kyc_document_status's new values are intentionally not removed on
    # downgrade — Postgres cannot drop individual enum values.
