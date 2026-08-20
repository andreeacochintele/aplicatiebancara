"""Add credit lifecycle tables.

Revision ID: 0015_credit_lifecycle
Revises: 0014_merge_cards_rewards
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_credit_lifecycle"
down_revision: Union[str, None] = "0014_merge_cards_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE loan_status ADD VALUE IF NOT EXISTS 'PAID'")

    sa.Enum("PENDING", "PAID", "PARTIAL", "OVERDUE", name="loan_installment_status").create(bind, checkfirst=True)
    sa.Enum("REGULAR", "EARLY_REPAYMENT", name="loan_payment_type").create(bind, checkfirst=True)
    installment_status = postgresql.ENUM(
        "PENDING",
        "PAID",
        "PARTIAL",
        "OVERDUE",
        name="loan_installment_status",
        create_type=False,
    )
    payment_type = postgresql.ENUM("REGULAR", "EARLY_REPAYMENT", name="loan_payment_type", create_type=False)

    op.add_column("loans", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("loans", sa.Column("maturity_date", sa.Date(), nullable=True))
    op.add_column("loans", sa.Column("next_payment_date", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE loans
        SET start_date = COALESCE(start_date, DATE(created_at)),
            maturity_date = COALESCE(maturity_date, DATE(created_at)),
            next_payment_date = COALESCE(next_payment_date, DATE(created_at))
        """
    )
    op.alter_column("loans", "start_date", nullable=False)
    op.alter_column("loans", "maturity_date", nullable=False)
    op.alter_column("loans", "next_payment_date", nullable=False)

    op.create_table(
        "loan_installments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("loan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("installment_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("payment_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("principal_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("interest_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("fees_amount", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("remaining_principal", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", installment_status, nullable=False, server_default="PENDING"),
        sa.UniqueConstraint("loan_id", "installment_number", name="uq_loan_installments_loan_number"),
    )
    op.create_table(
        "loan_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("loan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("principal_paid", sa.Numeric(18, 2), nullable=False),
        sa.Column("interest_paid", sa.Numeric(18, 2), nullable=False),
        sa.Column("fees_paid", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
        sa.Column("payment_type", payment_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("loan_payments")
    op.drop_table("loan_installments")
    op.drop_column("loans", "next_payment_date")
    op.drop_column("loans", "maturity_date")
    op.drop_column("loans", "start_date")
    sa.Enum(name="loan_payment_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="loan_installment_status").drop(op.get_bind(), checkfirst=True)
