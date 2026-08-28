"""Add MT940 to export_format (business transaction export gains an MT940
SWIFT statement format, alongside the existing CSV/XLSX/PDF).

Revision ID: 0043_export_format_mt940
Revises: 0042_wallet_balance_nonnegative
Create Date: 2026-08-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0043_export_format_mt940"
down_revision: Union[str, None] = "0042_wallet_balance_nonnegative"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE export_format ADD VALUE IF NOT EXISTS 'MT940'")


def downgrade() -> None:
    # Postgres cannot drop individual enum values — same limitation noted in
    # 0037_savings_goal_contributions.
    pass
