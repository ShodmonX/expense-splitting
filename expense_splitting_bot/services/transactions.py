from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from expense_splitting_bot.db.models import Member, Transaction, TransactionParticipant, TransactionType


async def create_transaction(
    session: AsyncSession,
    *,
    chat_id: int,
    type: TransactionType,
    amount_k: int,
    paid_by_member_id: int,
    participant_member_ids: list[int],
    note: Optional[str] = None,
) -> Transaction:
    if amount_k <= 0:
        raise ValueError("Summani musbat butun son sifatida kiriting.")
    participant_member_ids = sorted(set(int(x) for x in participant_member_ids))
    if not participant_member_ids:
        raise ValueError("Ishtirokchilar ro'yxati bo'sh bo'lmasligi kerak.")

    involved = set(participant_member_ids) | {int(paid_by_member_id)}
    existing = (
        await session.scalars(select(Member.id).where(Member.chat_id == chat_id, Member.id.in_(involved)))
    ).all()
    if len(existing) != len(involved):
        raise ValueError("Tanlangan a'zolarning barchasi shu guruhda bo'lishi kerak.")

    tx = Transaction(
        chat_id=chat_id,
        type=type,
        amount_k=int(amount_k),
        paid_by_member_id=int(paid_by_member_id),
        note=(note.strip() if note and note.strip() else None),
    )
    session.add(tx)
    await session.flush()

    session.add_all([TransactionParticipant(transaction_id=tx.id, member_id=mid) for mid in participant_member_ids])
    await session.flush()
    return tx


async def get_last_transactions(session: AsyncSession, *, chat_id: int, limit: int = 5) -> list[Transaction]:
    res = await session.scalars(
        select(Transaction)
        .where(Transaction.chat_id == chat_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(limit)
    )
    return list(res)

