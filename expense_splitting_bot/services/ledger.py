from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from expense_splitting_bot.db.models import Member, Transaction, TransactionParticipant, TransactionType


@dataclass(frozen=True)
class BalanceEntry:
    member_id: int
    balance_k: int  # positive owes, negative is owed


@dataclass(frozen=True)
class Transfer:
    from_member_id: int  # debtor
    to_member_id: int  # creditor
    amount_k: int


@dataclass(frozen=True)
class RoomBreakdownEntry:
    member_id: int
    total_share_k: int


async def compute_room_total_k(session: AsyncSession, *, chat_id: int) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(Transaction.amount_k), 0)).where(
            Transaction.chat_id == chat_id,
            Transaction.type == TransactionType.ROOM,
        )
    )
    return int(total or 0)


async def compute_balances(session: AsyncSession, *, chat_id: int) -> list[BalanceEntry]:
    member_ids = (
        await session.scalars(select(Member.id).where(Member.chat_id == chat_id))
    ).all()
    balances: dict[int, int] = {int(mid): 0 for mid in member_ids}

    tx_rows = (
        await session.execute(
            select(Transaction.id, Transaction.type, Transaction.amount_k, Transaction.paid_by_member_id).where(
                Transaction.chat_id == chat_id
            )
        )
    ).all()

    participant_rows = (
        await session.execute(
            select(TransactionParticipant.transaction_id, TransactionParticipant.member_id, Member.tg_user_id)
            .join(Member, Member.id == TransactionParticipant.member_id)
            .join(Transaction, Transaction.id == TransactionParticipant.transaction_id)
            .where(Transaction.chat_id == chat_id)
            .order_by(TransactionParticipant.transaction_id.asc(), Member.tg_user_id.asc())
        )
    ).all()

    participants_by_tx: dict[int, list[int]] = defaultdict(list)
    for tx_id, member_id, _tg_user_id in participant_rows:
        participants_by_tx[int(tx_id)].append(int(member_id))

    for tx_id, _type, amount_k, paid_by_member_id in tx_rows:
        tx_id_i = int(tx_id)
        amt = int(amount_k)
        payer = int(paid_by_member_id)
        if payer in balances:
            balances[payer] -= amt

        parts = participants_by_tx.get(tx_id_i, [])
        if not parts:
            continue
        n = len(parts)
        share = amt // n
        rem = amt % n
        for i, mid in enumerate(parts):
            balances[mid] += share + (1 if i < rem else 0)

    entries = [BalanceEntry(member_id=mid, balance_k=bal) for (mid, bal) in balances.items()]
    # positive first (owes most), then negative (is owed most), then zeros.
    entries.sort(key=lambda e: (0, -e.balance_k) if e.balance_k > 0 else (1, e.balance_k) if e.balance_k < 0 else (2, 0))
    return entries


def compute_settlement(entries: list[BalanceEntry]) -> list[Transfer]:
    creditors: list[list[int]] = []  # [member_id, to_receive]
    debtors: list[list[int]] = []  # [member_id, to_pay]

    for e in entries:
        if e.balance_k < 0:
            creditors.append([e.member_id, -e.balance_k])
        elif e.balance_k > 0:
            debtors.append([e.member_id, e.balance_k])

    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    out: list[Transfer] = []
    i = 0
    j = 0
    while i < len(debtors) and j < len(creditors):
        d_id, owe = debtors[i]
        c_id, recv = creditors[j]
        amt = owe if owe < recv else recv
        if amt:
            out.append(Transfer(from_member_id=d_id, to_member_id=c_id, amount_k=amt))
        owe -= amt
        recv -= amt
        debtors[i][1] = owe
        creditors[j][1] = recv
        if owe == 0:
            i += 1
        if recv == 0:
            j += 1
    return out


async def compute_room_breakdown(session: AsyncSession, *, chat_id: int) -> list[RoomBreakdownEntry]:
    # Computes how much each participant was assigned in ROOM transactions (sum of shares).
    tx_rows = (
        await session.execute(
            select(Transaction.id, Transaction.amount_k).where(
                Transaction.chat_id == chat_id,
                Transaction.type == TransactionType.ROOM,
            )
        )
    ).all()

    participant_rows = (
        await session.execute(
            select(TransactionParticipant.transaction_id, TransactionParticipant.member_id, Member.tg_user_id)
            .join(Member, Member.id == TransactionParticipant.member_id)
            .join(Transaction, Transaction.id == TransactionParticipant.transaction_id)
            .where(Transaction.chat_id == chat_id, Transaction.type == TransactionType.ROOM)
            .order_by(TransactionParticipant.transaction_id.asc(), Member.tg_user_id.asc())
        )
    ).all()

    parts_by_tx: dict[int, list[int]] = defaultdict(list)
    for tx_id, member_id, _tg_user_id in participant_rows:
        parts_by_tx[int(tx_id)].append(int(member_id))

    totals: dict[int, int] = defaultdict(int)
    for tx_id, amount_k in tx_rows:
        parts = parts_by_tx.get(int(tx_id), [])
        if not parts:
            continue
        amt = int(amount_k)
        n = len(parts)
        share = amt // n
        rem = amt % n
        for i, mid in enumerate(parts):
            totals[mid] += share + (1 if i < rem else 0)

    out = [RoomBreakdownEntry(member_id=mid, total_share_k=tot) for mid, tot in totals.items()]
    out.sort(key=lambda e: (-e.total_share_k, e.member_id))
    return out

