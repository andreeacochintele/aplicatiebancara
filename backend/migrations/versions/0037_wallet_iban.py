"""Add a sandbox IBAN to every wallet (current account), generated for
existing rows and required for new ones going forward.

Revision ID: 0037_wallet_iban
Revises: 0036_export_jobs_and_categories
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_wallet_iban"
down_revision: Union[str, None] = "0036_export_jobs_and_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.wallets.iban import generate_iban

    op.add_column("wallets", sa.Column("iban", sa.String(34), nullable=True))

    connection = op.get_bind()
    wallet_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM wallets")).fetchall()]
    used_ibans: set[str] = set()
    for wallet_id in wallet_ids:
        iban = generate_iban()
        while iban in used_ibans:
            iban = generate_iban()
        used_ibans.add(iban)
        connection.execute(sa.text("UPDATE wallets SET iban = :iban WHERE id = :id"), {"iban": iban, "id": wallet_id})

    op.alter_column("wallets", "iban", nullable=False)
    op.create_unique_constraint("uq_wallets_iban", "wallets", ["iban"])


def downgrade() -> None:
    op.drop_constraint("uq_wallets_iban", "wallets", type_="unique")
    op.drop_column("wallets", "iban")
