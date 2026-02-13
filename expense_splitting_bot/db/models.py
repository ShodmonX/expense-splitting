from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


UTC_NOW = sa.text("timezone('utc', now())")


class Base(DeclarativeBase):
    pass


class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        UniqueConstraint("tg_chat_id", name="uq_chats_tg_chat_id"),
        Index("ix_chats_tg_chat_id", "tg_chat_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Telegram chat id (group id) is a signed 64-bit integer.
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dashboard_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=UTC_NOW, nullable=False)

    members: Mapped[list[Member]] = relationship(back_populates="chat", cascade="all, delete-orphan")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="chat", cascade="all, delete-orphan")


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("chat_id", "tg_user_id", name="uq_members_chat_tg_user"),
        Index("ix_members_chat_tg_user", "chat_id", "tg_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tg_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_resident: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=UTC_NOW, nullable=False)

    chat: Mapped[Chat] = relationship(back_populates="members")

    paid_transactions: Mapped[list[Transaction]] = relationship(
        back_populates="paid_by_member",
        foreign_keys="Transaction.paid_by_member_id",
    )


class TransactionType(str, enum.Enum):
    ROOM = "ROOM"
    SPLIT = "SPLIT"
    TRANSFER = "TRANSFER"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_chat_id", "chat_id"),
        Index("ix_transactions_chat_created_at", "chat_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, name="transaction_type"), nullable=False)
    # Amount stored in thousands of UZS. Example: 12 -> 12k -> 12,000 UZS.
    amount_k: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_by_member_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=UTC_NOW, nullable=False)

    chat: Mapped[Chat] = relationship(back_populates="transactions")
    paid_by_member: Mapped[Member] = relationship(
        back_populates="paid_transactions",
        foreign_keys=[paid_by_member_id],
    )

    participants: Mapped[list[TransactionParticipant]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
    )

    participant_members: Mapped[list[Member]] = relationship(
        secondary="transaction_participants",
        viewonly=True,
    )


class TransactionParticipant(Base):
    __tablename__ = "transaction_participants"
    __table_args__ = (
        UniqueConstraint("transaction_id", "member_id", name="uq_tx_participant"),
        Index("ix_tx_participants_tx_id", "transaction_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )

    transaction: Mapped[Transaction] = relationship(back_populates="participants")
    member: Mapped[Member] = relationship()
