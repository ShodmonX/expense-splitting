from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from expense_splitting_bot.bot.keyboards import close_keyboard
from expense_splitting_bot.bot.utils import delete_later, safe_delete_message
from expense_splitting_bot.db.models import Chat
from expense_splitting_bot.services.ledger import compute_balances, compute_settlement
from expense_splitting_bot.services.members import list_members
from expense_splitting_bot.bot.text import member_label

router = Router(name=__name__)


def _require_group(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


@router.message(Command("balance"))
async def balance_cmd(message: Message, bot: Bot, session: AsyncSession, chat_db: Chat) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)

    members = await list_members(session, chat_id=chat_db.id)
    members_by_id = {m.id: m for m in members}
    balances = await compute_balances(session, chat_id=chat_db.id)

    lines = []
    for b in balances[:30]:
        m = members_by_id.get(b.member_id)
        name = member_label(m) if m else str(b.member_id)
        if b.balance_k > 0:
            lines.append(f"{name}: +{b.balance_k}k (beradi)")
        elif b.balance_k < 0:
            lines.append(f"{name}: {b.balance_k}k (oladi)")
        else:
            lines.append(f"{name}: 0k")
    if not lines:
        lines = ["Hali balans yo'q."]

    msg = await message.answer(
        "<b>Balanslar</b>\n<pre>" + "\n".join(lines) + "</pre>",
        parse_mode=ParseMode.HTML,
        reply_markup=close_keyboard(initiator_user_id=message.from_user.id),
    )
    delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=120)


@router.message(Command("settle"))
async def settle_cmd(message: Message, bot: Bot, session: AsyncSession, chat_db: Chat) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)

    members = await list_members(session, chat_id=chat_db.id)
    members_by_id = {m.id: m for m in members}
    balances = await compute_balances(session, chat_id=chat_db.id)
    transfers = compute_settlement(balances)

    lines = []
    for t in transfers[:30]:
        frm = members_by_id.get(t.from_member_id)
        to = members_by_id.get(t.to_member_id)
        lines.append(f"{member_label(frm) if frm else t.from_member_id} → {member_label(to) if to else t.to_member_id}: {t.amount_k}k")
    if not lines:
        lines = ["Hozircha kerak emas."]

    msg = await message.answer(
        "<b>Tavsiya etilgan to'lovlar</b>\n<pre>" + "\n".join(lines) + "</pre>",
        parse_mode=ParseMode.HTML,
        reply_markup=close_keyboard(initiator_user_id=message.from_user.id),
    )
    delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=120)

