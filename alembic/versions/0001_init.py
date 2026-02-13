"""init tables

Revision ID: 0001_init
Revises:
Create Date: 2026-02-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


UTC_NOW = sa.text("timezone('utc', now())")


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("dashboard_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.UniqueConstraint("tg_chat_id", name="uq_chats_tg_chat_id"),
    )
    op.create_index("ix_chats_tg_chat_id", "chats", ["tg_chat_id"])

    op.create_table(
        "members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("is_resident", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.UniqueConstraint("chat_id", "tg_user_id", name="uq_members_chat_tg_user"),
    )
    op.create_index("ix_members_chat_id", "members", ["chat_id"])
    op.create_index("ix_members_chat_tg_user", "members", ["chat_id", "tg_user_id"])

    # IMPORTANT:
    # Use the PostgreSQL-native ENUM type so we can disable implicit CREATE TYPE during
    # table DDL. We'll create it explicitly with checkfirst=True.
    tx_type = postgresql.ENUM("ROOM", "SPLIT", "TRANSFER", name="transaction_type", create_type=False)
    tx_type.create(op.get_bind(), checkfirst=True)
    

    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", tx_type, nullable=False),
        sa.Column("amount_k", sa.Integer(), nullable=False),
        sa.Column(
            "paid_by_member_id",
            sa.BigInteger(),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
    )
    op.create_index("ix_transactions_chat_id", "transactions", ["chat_id"])
    op.create_index("ix_transactions_chat_created_at", "transactions", ["chat_id", "created_at"])

    op.create_table(
        "transaction_participants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "transaction_id",
            sa.BigInteger(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.BigInteger(),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("transaction_id", "member_id", name="uq_tx_participant"),
    )
    op.create_index("ix_tx_participants_tx_id", "transaction_participants", ["transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_tx_participants_tx_id", table_name="transaction_participants")
    op.drop_table("transaction_participants")

    op.drop_index("ix_transactions_chat_created_at", table_name="transactions")
    op.drop_index("ix_transactions_chat_id", table_name="transactions")
    op.drop_table("transactions")

    tx_type = postgresql.ENUM("ROOM", "SPLIT", "TRANSFER", name="transaction_type", create_type=False)
    tx_type.drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_members_chat_tg_user", table_name="members")
    op.drop_index("ix_members_chat_id", table_name="members")
    op.drop_table("members")

    op.drop_index("ix_chats_tg_chat_id", table_name="chats")
    op.drop_table("chats")
