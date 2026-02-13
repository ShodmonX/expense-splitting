from __future__ import annotations

from typing import Optional

import sqlalchemy as sa
from aiogram.types import Chat as TgChat
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from expense_splitting_bot.db.models import Chat, Member


async def ensure_chat(session: AsyncSession, *, tg_chat: TgChat) -> Chat:
    insert_stmt = insert(Chat).values(
        tg_chat_id=tg_chat.id,
        title=tg_chat.title,
    )
    stmt = (
        insert_stmt.on_conflict_do_update(
            index_elements=[Chat.tg_chat_id],
            set_={"title": sa.func.coalesce(insert_stmt.excluded.title, Chat.title)},
        )
        .returning(Chat)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def upsert_member(session: AsyncSession, *, chat: Chat, user: TgUser) -> Member:
    username = user.username.lower() if user.username else None
    first_name = user.first_name if user.first_name else None

    insert_stmt = insert(Member).values(
        chat_id=chat.id,
        tg_user_id=user.id,
        username=username,
        first_name=first_name,
    )
    stmt = (
        insert_stmt.on_conflict_do_update(
            index_elements=[Member.chat_id, Member.tg_user_id],
            set_={
                "username": insert_stmt.excluded.username,
                "first_name": insert_stmt.excluded.first_name,
            },
        )
        .returning(Member)
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def list_members(session: AsyncSession, *, chat_id: int) -> list[Member]:
    res = await session.scalars(select(Member).where(Member.chat_id == chat_id).order_by(Member.tg_user_id.asc()))
    return list(res)


async def list_residents(session: AsyncSession, *, chat_id: int) -> list[Member]:
    res = await session.scalars(
        select(Member)
        .where(Member.chat_id == chat_id, Member.is_resident.is_(True))
        .order_by(Member.tg_user_id.asc())
    )
    return list(res)


async def get_member_by_id(session: AsyncSession, *, chat_id: int, member_id: int) -> Optional[Member]:
    return await session.scalar(select(Member).where(Member.chat_id == chat_id, Member.id == member_id))


async def get_member_by_tg_user_id(session: AsyncSession, *, chat_id: int, tg_user_id: int) -> Optional[Member]:
    return await session.scalar(select(Member).where(Member.chat_id == chat_id, Member.tg_user_id == tg_user_id))


async def toggle_resident(session: AsyncSession, *, chat_id: int, member_id: int) -> Optional[Member]:
    m = await get_member_by_id(session, chat_id=chat_id, member_id=member_id)
    if m is None:
        return None
    m.is_resident = not bool(m.is_resident)
    await session.flush()
    return m

