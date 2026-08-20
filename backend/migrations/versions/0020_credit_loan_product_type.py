"""Add loan product type to credit applications.

Revision ID: 0020_credit_loan_product_type
Revises: 0019_credit_profile_currency
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_credit_loan_product_type"
down_revision: Union[str, None] = "0019_credit_profile_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

loan_product_type = sa.Enum(
    "PERSONAL_LOAN",
    "MORTGAGE",
    "AUTO_LOAN",
    "STUDENT_LOAN",
    "HOME_IMPROVEMENT",
    "DEBT_CONSOLIDATION",
    name="loan_product_type",
)


def upgrade() -> None:
    bind = op.get_bind()
    loan_product_type.create(bind, checkfirst=True)
    op.add_column("credit_applications", sa.Column("loan_product_type", loan_product_type, nullable=True))
    op.execute(
        "UPDATE credit_applications "
        "SET loan_product_type = 'PERSONAL_LOAN' "
        "WHERE type = 'PERSONAL_LOAN' AND loan_product_type IS NULL"
    )


def downgrade() -> None:
    op.drop_column("credit_applications", "loan_product_type")
    loan_product_type.drop(op.get_bind(), checkfirst=True)
