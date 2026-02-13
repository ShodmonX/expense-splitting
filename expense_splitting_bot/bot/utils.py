from __future__ import annotations

import asyncio
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError


async def safe_delete_message(bot: Bot, *, chat_id: int, message_id: int) -> bool:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except (TelegramBadRequest, TelegramForbiddenError):
        return False


def delete_later(bot: Bot, *, chat_id: int, message_id: int, delay_seconds: float) -> None:
    async def _job() -> None:
        await asyncio.sleep(delay_seconds)
        await safe_delete_message(bot, chat_id=chat_id, message_id=message_id)

    asyncio.create_task(_job())

