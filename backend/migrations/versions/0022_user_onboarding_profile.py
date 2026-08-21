"""Add user onboarding and profile tables.

Revision ID: 0022_user_onboarding_profile
Revises: 0021_merge_heads
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_user_onboarding_profile"
down_revision: Union[str, Sequence[str], None] = "0021_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    kyc_document_status = postgresql.ENUM("NOT_STARTED", "PLACEHOLDER", name="kyc_document_status")
    employment_status = postgresql.ENUM(
        "EMPLOYED",
        "SELF_EMPLOYED",
        "STUDENT",
        "UNEMPLOYED",
        "RETIRED",
        "OTHER",
        name="employment_status",
    )
    kyc_document_status.create(op.get_bind(), checkfirst=True)
    employment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_onboarding_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pending_step", sa.Integer(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("step_4_skipped", sa.Boolean(), nullable=False),
        sa.Column("identity_document_status", kyc_document_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_onboarding_states_user_id"), "user_onboarding_states", ["user_id"], unique=True)

    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cnp", sa.String(length=13), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("citizenship", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_profiles_cnp"), "user_profiles", ["cnp"], unique=True)
    op.create_index(op.f("ix_user_profiles_user_id"), "user_profiles", ["user_id"], unique=True)

    op.create_table(
        "user_addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("street_number", sa.String(length=32), nullable=True),
        sa.Column("building", sa.String(length=32), nullable=True),
        sa.Column("staircase", sa.String(length=32), nullable=True),
        sa.Column("apartment", sa.String(length=32), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_addresses_user_id"), "user_addresses", ["user_id"], unique=True)

    op.create_table(
        "user_employment_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occupation", sa.String(length=100), nullable=True),
        sa.Column("employer", sa.String(length=255), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("employment_status", employment_status, nullable=True),
        sa.Column("income_source", sa.String(length=100), nullable=True),
        sa.Column("approximate_monthly_income", sa.Numeric(18, 2), nullable=True),
        sa.Column("account_purpose", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_employment_profiles_user_id"), "user_employment_profiles", ["user_id"], unique=True)

    # Users already present before this feature existed should not be forced
    # through onboarding. New registrations create their own incomplete state
    # from the application service after this migration is installed.
    op.execute(
        """
        INSERT INTO user_onboarding_states (
            id,
            user_id,
            pending_step,
            completed,
            step_4_skipped,
            identity_document_status,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            users.id,
            NULL,
            TRUE,
            FALSE,
            'NOT_STARTED',
            now(),
            now()
        FROM users
        ON CONFLICT (user_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_profiles (id, user_id, created_at, updated_at)
        SELECT gen_random_uuid(), users.id, now(), now()
        FROM users
        ON CONFLICT (user_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_addresses (id, user_id, created_at, updated_at)
        SELECT gen_random_uuid(), users.id, now(), now()
        FROM users
        ON CONFLICT (user_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_employment_profiles (id, user_id, created_at, updated_at)
        SELECT gen_random_uuid(), users.id, now(), now()
        FROM users
        ON CONFLICT (user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_employment_profiles_user_id"), table_name="user_employment_profiles")
    op.drop_table("user_employment_profiles")
    op.drop_index(op.f("ix_user_addresses_user_id"), table_name="user_addresses")
    op.drop_table("user_addresses")
    op.drop_index(op.f("ix_user_profiles_user_id"), table_name="user_profiles")
    op.drop_index(op.f("ix_user_profiles_cnp"), table_name="user_profiles")
    op.drop_table("user_profiles")
    op.drop_index(op.f("ix_user_onboarding_states_user_id"), table_name="user_onboarding_states")
    op.drop_table("user_onboarding_states")
    postgresql.ENUM(name="employment_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="kyc_document_status").drop(op.get_bind(), checkfirst=True)
