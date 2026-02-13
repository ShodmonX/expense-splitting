from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from expense_splitting_bot.bot.dashboard_render import render_dashboard
from expense_splitting_bot.db.models import Chat, Member
from expense_splitting_bot.services.ledger import compute_balances, compute_room_total_k, compute_settlement
from expense_splitting_bot.services.members import list_members, list_residents

logger = logging.getLogger(__name__)


@dataclass
class _ChatDashState:
    lock: asyncio.Lock
    pending: Optional[asyncio.Task]
    dirty: bool
    last_edit_monotonic: float


class DashboardManager:
    def __init__(
        self,
        *,
        bot: Bot,
        sessionmaker: async_sessionmaker[AsyncSession],
        debounce_seconds: float,
    ) -> None:
        self._bot = bot
        self._sessionmaker = sessionmaker
        self._debounce = debounce_seconds
        self._states: dict[int, _ChatDashState] = {}

    def schedule(self, tg_chat_id: int) -> None:
        state = self._states.get(tg_chat_id)
        if state is None:
            state = _ChatDashState(lock=asyncio.Lock(), pending=None, dirty=False, last_edit_monotonic=0.0)
            self._states[tg_chat_id] = state

        state.dirty = True
        if state.pending is None or state.pending.done():
            state.pending = asyncio.create_task(self._worker(tg_chat_id))

    async def update_now(self, tg_chat_id: int) -> None:
        await self._update(tg_chat_id)
        state = self._states.get(tg_chat_id)
        if state is not None:
            state.last_edit_monotonic = time.monotonic()

    async def _worker(self, tg_chat_id: int) -> None:
        try:
            while True:
                state = self._states.get(tg_chat_id)
                if state is None:
                    return

                wait_s = max(0.0, self._debounce - (time.monotonic() - state.last_edit_monotonic))
                await asyncio.sleep(wait_s)

                async with state.lock:
                    if not state.dirty:
                        return
                    state.dirty = False

                await self._update(tg_chat_id)

                async with state.lock:
                    state.last_edit_monotonic = time.monotonic()
        except Exception:
            logger.exception("Dashboard worker crashed for tg_chat_id=%s", tg_chat_id)

    async def _update(self, tg_chat_id: int) -> None:
        async with self._sessionmaker() as session:
            chat = await session.scalar(select(Chat).where(Chat.tg_chat_id == tg_chat_id))
            if chat is None:
                # If someone calls schedule before middleware upsert (rare), just no-op.
                return

            members = await list_members(session, chat_id=chat.id)
            residents = await list_residents(session, chat_id=chat.id)
            balances = await compute_balances(session, chat_id=chat.id)
            transfers = compute_settlement(balances)
            room_total_k = await compute_room_total_k(session, chat_id=chat.id)
            members_by_id: dict[int, Member] = {m.id: m for m in members}

            text = render_dashboard(
                chat_title=chat.title,
                residents=residents,
                room_total_k=room_total_k,
                balances=balances,
                transfers=transfers,
                members_by_id=members_by_id,
            )

            if chat.dashboard_message_id is None:
                msg = await self._bot.send_message(
                    chat_id=tg_chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                chat.dashboard_message_id = msg.message_id
                await session.commit()
                try:
                    await self._bot.pin_chat_message(chat_id=tg_chat_id, message_id=msg.message_id, disable_notification=True)
                except Exception:
                    pass
                return

            try:
                await self._bot.edit_message_text(
                    chat_id=tg_chat_id,
                    message_id=chat.dashboard_message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    return
                # Message deleted or not editable: recreate.
                old_id = chat.dashboard_message_id
                msg = await self._bot.send_message(
                    chat_id=tg_chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                chat.dashboard_message_id = msg.message_id
                await session.commit()
                try:
                    if old_id and old_id != msg.message_id:
                        await self._bot.unpin_chat_message(chat_id=tg_chat_id, message_id=old_id)
                    await self._bot.pin_chat_message(chat_id=tg_chat_id, message_id=msg.message_id, disable_notification=True)
                except Exception:
                    pass
