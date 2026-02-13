from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from expense_splitting_bot.bot.callbacks import PageCb, SetupDoneCb, SetupToggleResidentCb
from expense_splitting_bot.bot.dashboard import DashboardManager
from expense_splitting_bot.bot.keyboards import setup_keyboard
from expense_splitting_bot.bot.utils import delete_later, safe_delete_message
from expense_splitting_bot.db.models import Chat, Member
from expense_splitting_bot.services.ledger import compute_balances, compute_room_breakdown, compute_room_total_k, compute_settlement
from expense_splitting_bot.services.members import get_member_by_tg_user_id, list_members, toggle_resident, upsert_member
from expense_splitting_bot.bot.text import member_label
from expense_splitting_bot.bot.keyboards import close_keyboard

router = Router(name=__name__)


def _require_group(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def _is_admin(bot: Bot, *, tg_chat_id: int, tg_user_id: int) -> bool:
    cm = await bot.get_chat_member(chat_id=tg_chat_id, user_id=tg_user_id)
    return cm.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)


@router.message(Command("setup"))
async def setup_cmd(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
    member_db: Member,
) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)

    if not await _is_admin(bot, tg_chat_id=message.chat.id, tg_user_id=message.from_user.id):
        msg = await message.answer("Bu buyruq faqat adminlar uchun.")
        delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=5)
        return

    members = await list_members(session, chat_id=chat_db.id)
    if not members:
        msg = await message.answer("Hali a'zolar yo'q. Avval guruhda yozishsin, keyin /setup qiling.")
        delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=7)
        return

    wizard = await message.answer(
        "<b>/setup</b>\nResident (🏠) bo'lganlarni tanlang (toggle).",
        parse_mode=ParseMode.HTML,
        reply_markup=setup_keyboard(initiator_user_id=message.from_user.id, members=members, page=0),
    )
    # Wizard message will be deleted on Save/Cancel.
    delete_later(bot, chat_id=wizard.chat.id, message_id=wizard.message_id, delay_seconds=600)


@router.callback_query(PageCb.filter())
async def setup_page_cb(
    callback: CallbackQuery,
    callback_data: PageCb,
    session: AsyncSession,
    chat_db: Chat,
) -> None:
    if callback_data.flow != "setup":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    members = await list_members(session, chat_id=chat_db.id)
    await callback.message.edit_reply_markup(
        reply_markup=setup_keyboard(initiator_user_id=callback.from_user.id, members=members, page=callback_data.page)
    )
    await callback.answer()


@router.callback_query(SetupToggleResidentCb.filter())
async def setup_toggle_cb(
    callback: CallbackQuery,
    callback_data: SetupToggleResidentCb,
    session: AsyncSession,
    chat_db: Chat,
) -> None:
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    await toggle_resident(session, chat_id=chat_db.id, member_id=callback_data.member_id)
    members = await list_members(session, chat_id=chat_db.id)
    await callback.message.edit_reply_markup(
        reply_markup=setup_keyboard(initiator_user_id=callback.from_user.id, members=members, page=callback_data.page)
    )
    await callback.answer("Yangilandi.")


@router.callback_query(SetupDoneCb.filter())
async def setup_done_cb(
    callback: CallbackQuery,
    callback_data: SetupDoneCb,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
    dashboard: DashboardManager,
) -> None:
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    # close wizard
    await safe_delete_message(bot, chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    dashboard.schedule(callback.message.chat.id)
    await callback.answer("Saqlangan.")


@router.message(Command("add_member"))
async def add_member_cmd(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
    dashboard: DashboardManager,
) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)

    if not await _is_admin(bot, tg_chat_id=message.chat.id, tg_user_id=message.from_user.id):
        msg = await message.answer("Bu buyruq faqat adminlar uchun.")
        delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=5)
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        msg = await message.answer("Foydalanuvchining xabariga reply qilib /add_member yozing.")
        delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=7)
        return

    u = message.reply_to_message.from_user
    if u.is_bot:
        msg = await message.answer("Botni qo'shib bo'lmaydi.")
        delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=5)
        return

    existing = await get_member_by_tg_user_id(session, chat_id=chat_db.id, tg_user_id=u.id)
    if existing is None:
        await upsert_member(session, chat=chat_db, user=u)

    msg = await message.answer(f"A'zo qo'shildi: {member_label(existing) if existing else (('@'+u.username) if u.username else u.first_name)}")
    delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=5)
    dashboard.schedule(message.chat.id)


@router.message(Command("report"))
async def report_cmd(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)

    if not await _is_admin(bot, tg_chat_id=message.chat.id, tg_user_id=message.from_user.id):
        msg = await message.answer("Bu buyruq faqat adminlar uchun.")
        delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=5)
        return

    members = await list_members(session, chat_id=chat_db.id)
    members_by_id = {m.id: m for m in members}

    room_total_k = await compute_room_total_k(session, chat_id=chat_db.id)
    breakdown = await compute_room_breakdown(session, chat_id=chat_db.id)
    balances = await compute_balances(session, chat_id=chat_db.id)
    transfers = compute_settlement(balances)

    breakdown_lines = []
    for e in breakdown[:20]:
        m = members_by_id.get(e.member_id)
        breakdown_lines.append(f"{member_label(m) if m else e.member_id}: {e.total_share_k}k")
    if not breakdown_lines:
        breakdown_lines = ["Hali ROOM tranzaksiyalar yo'q."]

    bal_lines = []
    for b in balances[:20]:
        m = members_by_id.get(b.member_id)
        bal_lines.append(f"{member_label(m) if m else b.member_id}: {b.balance_k}k")

    settle_lines = []
    for t in transfers[:20]:
        settle_lines.append(
            f"{member_label(members_by_id.get(t.from_member_id))} -> {member_label(members_by_id.get(t.to_member_id))}: {t.amount_k}k"
        )
    if not settle_lines:
        settle_lines = ["Kerak emas."]

    balances_block = chr(10).join(bal_lines) if bal_lines else "Yo'q"
    text = (
        f"<b>Hisobot</b>\n\n"
        f"<b>ROOM jami:</b> {room_total_k}k\n\n"
        f"<b>ROOM ulushlar (residentlar):</b>\n<pre>{chr(10).join(breakdown_lines)}</pre>\n"
        f"<b>Balanslar:</b>\n<pre>{balances_block}</pre>\n"
        f"<b>Tavsiya etilgan to'lovlar:</b>\n<pre>{chr(10).join(settle_lines)}</pre>"
    )
    msg = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=close_keyboard(initiator_user_id=message.from_user.id))
    # user can close; also auto-delete later
    delete_later(bot, chat_id=msg.chat.id, message_id=msg.message_id, delay_seconds=180)
