from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from expense_splitting_bot.bot.callbacks import ConfirmCb, DigitCb, NumActionCb, PageCb, PickMemberCb
from expense_splitting_bot.bot.dashboard import DashboardManager
from expense_splitting_bot.bot.keyboards import confirm_keyboard, members_keyboard, numeric_keyboard
from expense_splitting_bot.bot.utils import safe_delete_message
from expense_splitting_bot.db.models import Chat, Member, TransactionType
from expense_splitting_bot.services.members import list_members, list_residents
from expense_splitting_bot.services.transactions import create_transaction
from expense_splitting_bot.bot.text import member_label

router = Router(name=__name__)


def _require_group(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def _format_amount_line(amount_k_str: str) -> str:
    v = amount_k_str if amount_k_str else "0"
    return f"Summa (k): <b>{v}k</b>"


@router.message(Command("room"))
async def room_cmd(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
    member_db: Member,
    state: FSMContext,
) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)
    await state.clear()
    await state.update_data(
        initiator_user_id=message.from_user.id,
        amount_k_str="",
        paid_by_member_id=None,
    )
    wizard = await message.answer(
        "<b>ROOM (xona harajati)</b>\n"
        f"{_format_amount_line('')}\n\n"
        "Summani tugmalar bilan kiriting (masalan: 403 -> 403k).",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=message.from_user.id, field="room_amount_k"),
    )
    await state.update_data(wizard_message_id=wizard.message_id)


@router.callback_query(DigitCb.filter())
async def room_digit_cb(callback: CallbackQuery, callback_data: DigitCb, state: FSMContext) -> None:
    if callback_data.field != "room_amount_k":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    amount_s = str(data.get("amount_k_str") or "")
    if len(amount_s) >= 7:
        await callback.answer("Juda katta summa.")
        return
    amount_s = (amount_s + str(callback_data.digit)).lstrip("0")
    await state.update_data(amount_k_str=amount_s)
    await callback.message.edit_text(
        "<b>ROOM (xona harajati)</b>\n"
        f"{_format_amount_line(amount_s)}\n\n"
        "Summani tugmalar bilan kiriting.",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=callback.from_user.id, field="room_amount_k"),
    )
    await callback.answer()


@router.callback_query(NumActionCb.filter())
async def room_num_action_cb(
    callback: CallbackQuery,
    callback_data: NumActionCb,
    session: AsyncSession,
    chat_db: Chat,
    state: FSMContext,
) -> None:
    if callback_data.field != "room_amount_k":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return

    data = await state.get_data()
    amount_s = str(data.get("amount_k_str") or "")

    if callback_data.action == "back":
        amount_s = amount_s[:-1]
        await state.update_data(amount_k_str=amount_s)
    elif callback_data.action == "clear":
        amount_s = ""
        await state.update_data(amount_k_str=amount_s)
    elif callback_data.action == "ok":
        if not amount_s:
            await callback.answer("Summani kiriting.", show_alert=True)
            return
        amount_k = int(amount_s)
        if amount_k <= 0:
            await callback.answer("Summani to'g'ri kiriting.", show_alert=True)
            return
        members = await list_members(session, chat_id=chat_db.id)
        await state.update_data(room_amount_k=amount_k, room_payer_page=0)
        await callback.message.edit_text(
            "<b>ROOM</b>\n"
            f"Summa: <b>{amount_k}k</b>\n\n"
            "Kim to'ladi?",
            parse_mode=ParseMode.HTML,
            reply_markup=members_keyboard(
                initiator_user_id=callback.from_user.id,
                flow="room_payer",
                field="paid_by",
                members=members,
                page=0,
            ),
        )
        await callback.answer()
        return
    else:
        return

    await callback.message.edit_text(
        "<b>ROOM (xona harajati)</b>\n"
        f"{_format_amount_line(amount_s)}\n\n"
        "Summani tugmalar bilan kiriting.",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=callback.from_user.id, field="room_amount_k"),
    )
    await callback.answer()


@router.callback_query(PageCb.filter())
async def room_page_cb(callback: CallbackQuery, callback_data: PageCb, session: AsyncSession, chat_db: Chat) -> None:
    if callback_data.flow != "room_payer":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    members = await list_members(session, chat_id=chat_db.id)
    await callback.message.edit_reply_markup(
        reply_markup=members_keyboard(
            initiator_user_id=callback.from_user.id,
            flow="room_payer",
            field="paid_by",
            members=members,
            page=callback_data.page,
        )
    )
    await callback.answer()


@router.callback_query(PickMemberCb.filter())
async def room_pick_payer_cb(
    callback: CallbackQuery,
    callback_data: PickMemberCb,
    session: AsyncSession,
    chat_db: Chat,
    state: FSMContext,
) -> None:
    if callback_data.field != "paid_by":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    amount_k = int(data.get("room_amount_k") or 0)
    if amount_k <= 0:
        await callback.answer("Sessiya eskirgan. /room qayta bosing.", show_alert=True)
        return

    residents = await list_residents(session, chat_id=chat_db.id)
    if not residents:
        await callback.answer("Residentlar tanlanmagan. /setup qiling.", show_alert=True)
        return

    payer = next((m for m in await list_members(session, chat_id=chat_db.id) if m.id == callback_data.member_id), None)
    await state.update_data(paid_by_member_id=callback_data.member_id)

    await callback.message.edit_text(
        "<b>ROOM</b>\n"
        f"Summa: <b>{amount_k}k</b>\n"
        f"To'lovchi: <b>{member_label(payer) if payer else callback_data.member_id}</b>\n"
        f"Ishtirokchilar: <b>{len(residents)}</b> (barchasi resident)\n\n"
        "Tasdiqlaysizmi?",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_keyboard(initiator_user_id=callback.from_user.id, flow="room"),
    )
    await callback.answer()


@router.callback_query(ConfirmCb.filter())
async def room_confirm_cb(
    callback: CallbackQuery,
    callback_data: ConfirmCb,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
    state: FSMContext,
    dashboard: DashboardManager,
) -> None:
    if callback_data.flow != "room":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    amount_k = int(data.get("room_amount_k") or 0)
    paid_by_member_id = data.get("paid_by_member_id")
    if amount_k <= 0 or not paid_by_member_id:
        await callback.answer("Sessiya eskirgan. /room qayta bosing.", show_alert=True)
        return

    residents = await list_residents(session, chat_id=chat_db.id)
    if not residents:
        await callback.answer("Residentlar tanlanmagan. /setup qiling.", show_alert=True)
        return

    try:
        await create_transaction(
            session,
            chat_id=chat_db.id,
            type=TransactionType.ROOM,
            amount_k=amount_k,
            paid_by_member_id=int(paid_by_member_id),
            participant_member_ids=[m.id for m in residents],
            note=None,
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    # Clean up wizard message.
    if callback.message:
        await safe_delete_message(bot, chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await state.clear()
    dashboard.schedule(callback.message.chat.id)
    await callback.answer("Saqlandi.")
