from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage

from expense_splitting_bot.bot.dashboard import DashboardManager
from expense_splitting_bot.bot.middlewares import DbSessionMiddleware, UpsertChatMemberMiddleware
from expense_splitting_bot.bot.routers import all_routers
from expense_splitting_bot.config import settings
from expense_splitting_bot.db.session import SessionMaker
from expense_splitting_bot.logging import configure_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging(settings.log_level)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        try:
            me = await bot.get_me()
        except TelegramUnauthorizedError as e:
            logger.error("Telegram Unauthorized. Check BOT_TOKEN in .env (BotFather token). %s", e)
            raise

        bot_username = (me.username or "").strip()
        if not bot_username:
            raise RuntimeError("Bot username is empty; cannot parse @BotName quick-add messages.")

        dp = Dispatcher(storage=MemoryStorage())

        dp.update.middleware(DbSessionMiddleware(SessionMaker))
        dp.message.middleware(UpsertChatMemberMiddleware())
        dp.callback_query.middleware(UpsertChatMemberMiddleware())

        dashboard = DashboardManager(
            bot=bot,
            sessionmaker=SessionMaker,
            debounce_seconds=settings.dashboard_debounce_seconds,
        )

        dp.workflow_data.update({"dashboard": dashboard})

        for r in all_routers():
            dp.include_router(r)

        logger.info("Starting bot as @%s", bot_username)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
