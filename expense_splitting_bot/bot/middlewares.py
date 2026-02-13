from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from expense_splitting_bot.services.members import ensure_chat, upsert_member


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self._sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._sessionmaker() as session:
            try:
                data["session"] = session
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class UpsertChatMemberMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]

        tg_chat = None
        tg_user = None
        sender_chat = None

        if isinstance(event, Message):
            tg_chat = event.chat
            tg_user = event.from_user
            sender_chat = event.sender_chat
        elif isinstance(event, CallbackQuery) and event.message:
            tg_chat = event.message.chat
            tg_user = event.from_user
            sender_chat = event.message.sender_chat

        # Do NOT auto-add anonymous admins, channels, sender_chat messages.
        if tg_chat is None or tg_user is None or sender_chat is not None:
            return await handler(event, data)
        if tg_user.is_bot:
            return await handler(event, data)

        chat_db = await ensure_chat(session, tg_chat=tg_chat)
        member_db = await upsert_member(session, chat=chat_db, user=tg_user)
        data["chat_db"] = chat_db
        data["member_db"] = member_db
        return await handler(event, data)

