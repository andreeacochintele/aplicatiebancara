"""Create business_profiles (architecture.md's Business Profiles table):
company_name/tax_id/registration_number/business_category for BUSINESS
accounts, plus representative_name and is_active. One-to-many with User (a
user can represent more than one company) — is_active marks the currently
selected one, same invariant as Wallet.is_main.

Revision ID: 0044_business_profiles
Revises: 0043_export_format_mt940
Create Date: 2026-08-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_business_profiles"
down_revision: Union[str, None] = "0043_export_format_mt940"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("representative_name", sa.String(length=200), nullable=True),
        sa.Column("tax_id", sa.String(length=50), nullable=True),
        sa.Column("registration_number", sa.String(length=50), nullable=True),
        sa.Column("business_category", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_business_profiles_user_id", "business_profiles", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_business_profiles_user_id", table_name="business_profiles")
    op.drop_table("business_profiles")
