"""Backfill existing wallet IBANs from the old AURO bank code to EASY.

Every wallet IBAN generated before today's AURO -> EASY rebrand
(backend/app/wallets/iban.py) still embeds the old bank code. New wallets
already get EASY-coded IBANs from the app; this is a one-time data fix for
wallets created earlier — keeps each wallet's existing 16-digit account
number and recomputes the 2-digit checksum for the new bank code (same
ISO 7064 mod-97-10 algorithm as generate_iban(), with "EASY"/"AURO" and
"RO" pre-converted to digits per letter, same as the mirrored Supabase
script: E=14, A=10, S=28, Y=34 / A=10, U=30, R=27, O=24).

Revision ID: 0041_iban_easy_backfill
Revises: 0040_merge_heads
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0041_iban_easy_backfill"
down_revision: Union[str, None] = "0040_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE wallets
        SET iban = 'RO'
            || lpad((98 - ((14102834 || substring(iban from 9 for 16) || '272400')::numeric % 97))::text, 2, '0')
            || 'EASY'
            || substring(iban from 9 for 16)
        WHERE substring(iban from 5 for 4) = 'AURO'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE wallets
        SET iban = 'RO'
            || lpad((98 - ((10302724 || substring(iban from 9 for 16) || '272400')::numeric % 97))::text, 2, '0')
            || 'AURO'
            || substring(iban from 9 for 16)
        WHERE substring(iban from 5 for 4) = 'EASY'
        """
    )
