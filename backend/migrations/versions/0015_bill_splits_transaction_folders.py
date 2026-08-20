"""Add bill splits and transaction folders.

Revision ID: 0015_bill_splits_folders
Revises: 0014_merge_cards_rewards
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_bill_splits_folders"
down_revision: Union[str, None] = "0014_merge_cards_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bill_split_status = sa.Enum("OPEN", "SETTLED", "CANCELLED", name="bill_split_status")
    participant_status = sa.Enum("PENDING", "PAID", "DECLINED", name="bill_split_participant_status")
    bill_split_status.create(op.get_bind(), checkfirst=True)
    participant_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bill_splits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", bill_split_status, nullable=False, server_default="OPEN"),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_bill_splits_owner_user_id", "bill_splits", ["owner_user_id"])
    op.create_index("ix_bill_splits_source_transaction_id", "bill_splits", ["source_transaction_id"])

    op.create_table(
        "bill_split_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bill_split_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bill_splits.id"), nullable=False),
        sa.Column("participant_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", participant_status, nullable=False, server_default="PENDING"),
        sa.Column("paid_transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_bill_split_participants_split_id", "bill_split_participants", ["bill_split_id"])
    op.create_index("ix_bill_split_participants_user_id", "bill_split_participants", ["participant_user_id"])

    op.create_table(
        "transaction_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_transaction_folders_owner_name"),
    )
    op.create_index("ix_transaction_folders_owner_user_id", "transaction_folders", ["owner_user_id"])

    op.create_table(
        "transaction_folder_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transaction_folders.id"), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("folder_id", "transaction_id", name="uq_transaction_folder_items_folder_transaction"),
    )
    op.create_index("ix_transaction_folder_items_folder_id", "transaction_folder_items", ["folder_id"])
    op.create_index("ix_transaction_folder_items_transaction_id", "transaction_folder_items", ["transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_transaction_folder_items_transaction_id", table_name="transaction_folder_items")
    op.drop_index("ix_transaction_folder_items_folder_id", table_name="transaction_folder_items")
    op.drop_table("transaction_folder_items")
    op.drop_index("ix_transaction_folders_owner_user_id", table_name="transaction_folders")
    op.drop_table("transaction_folders")
    op.drop_index("ix_bill_split_participants_user_id", table_name="bill_split_participants")
    op.drop_index("ix_bill_split_participants_split_id", table_name="bill_split_participants")
    op.drop_table("bill_split_participants")
    op.drop_index("ix_bill_splits_source_transaction_id", table_name="bill_splits")
    op.drop_index("ix_bill_splits_owner_user_id", table_name="bill_splits")
    op.drop_table("bill_splits")
    sa.Enum(name="bill_split_participant_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="bill_split_status").drop(op.get_bind(), checkfirst=True)
