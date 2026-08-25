"""Store uploaded credit document content.

Revision ID: 0032_credit_document_content
Revises: 0031_credit_documents
Create Date: 2026-08-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_credit_document_content"
down_revision: Union[str, None] = "0031_credit_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("credit_documents", sa.Column("content_base64", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("credit_documents", "content_base64")
