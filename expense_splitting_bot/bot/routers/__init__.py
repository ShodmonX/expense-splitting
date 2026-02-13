from __future__ import annotations

from aiogram import Router

from expense_splitting_bot.bot.routers.admin import router as admin_router
from expense_splitting_bot.bot.routers.room import router as room_router
from expense_splitting_bot.bot.routers.split import router as split_router
from expense_splitting_bot.bot.routers.pay import router as pay_router
from expense_splitting_bot.bot.routers.public import router as public_router
from expense_splitting_bot.bot.routers.common_callbacks import router as common_callbacks_router


def all_routers() -> list[Router]:
    return [
        common_callbacks_router,
        admin_router,
        room_router,
        split_router,
        pay_router,
        public_router,
    ]

