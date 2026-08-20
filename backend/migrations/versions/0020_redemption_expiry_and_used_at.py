"""Add benefit_redemptions.expires_at and used_at.

Redeemed vouchers (BenefitRedemption.redemption_code) are now real,
time-boxed codes: expires_at is set 30 days out at redemption time, and
used_at is set (by the user, from the new "My vouchers" panel) once the
voucher has actually been used. A voucher's status is derived from these
two columns rather than stored directly (VALID / USED / EXPIRED).

Revision ID: 0020_redemption_expiry
Revises: 0019_referral_and_proof_codes
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_redemption_expiry"
down_revision: Union[str, None] = "0019_referral_and_proof_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("benefit_redemptions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("benefit_redemptions", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("benefit_redemptions", "used_at")
    op.drop_column("benefit_redemptions", "expires_at")
