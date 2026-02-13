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
from expense_splitting_bot.db.models import Chat, TransactionType
from expense_splitting_bot.services.members import list_members
from expense_splitting_bot.services.transactions import create_transaction
from expense_splitting_bot.bot.text import member_label

router = Router(name=__name__)


def _require_group(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


@router.message(Command("pay"))
async def pay_cmd(message: Message, bot: Bot, session: AsyncSession, chat_db: Chat, state: FSMContext) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)
    await state.clear()
    await state.update_data(
        initiator_user_id=message.from_user.id,
        pay_payer_member_id=None,
        pay_receiver_member_id=None,
        pay_amount_k_str="",
    )
    members = await list_members(session, chat_id=chat_db.id)
    wizard = await message.answer(
        "<b>PAY (o'tkazma)</b>\nKim to'laydi (payer)?",
        parse_mode=ParseMode.HTML,
        reply_markup=members_keyboard(
            initiator_user_id=message.from_user.id,
            flow="pay_payer",
            field="payer",
            members=members,
            page=0,
        ),
    )
    await state.update_data(wizard_message_id=wizard.message_id)


@router.callback_query(PageCb.filter())
async def pay_pages_cb(callback: CallbackQuery, callback_data: PageCb, session: AsyncSession, chat_db: Chat) -> None:
    if callback.from_user.id != callback_data.initiator:
        return
    if callback_data.flow not in ("pay_payer", "pay_receiver"):
        return
    members = await list_members(session, chat_id=chat_db.id)
    field = "payer" if callback_data.flow == "pay_payer" else "receiver"
    await callback.message.edit_reply_markup(
        reply_markup=members_keyboard(
            initiator_user_id=callback.from_user.id,
            flow=callback_data.flow,
            field=field,
            members=members,
            page=callback_data.page,
        )
    )
    await callback.answer()


@router.callback_query(PickMemberCb.filter())
async def pay_pick_member_cb(callback: CallbackQuery, callback_data: PickMemberCb, session: AsyncSession, chat_db: Chat, state: FSMContext) -> None:
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return

    members = await list_members(session, chat_id=chat_db.id)

    if callback_data.field == "payer":
        await state.update_data(pay_payer_member_id=callback_data.member_id)
        await callback.message.edit_text(
            "<b>PAY</b>\nKim oladi (receiver)?",
            parse_mode=ParseMode.HTML,
            reply_markup=members_keyboard(
                initiator_user_id=callback.from_user.id,
                flow="pay_receiver",
                field="receiver",
                members=members,
                page=0,
            ),
        )
        await callback.answer()
        return

    if callback_data.field == "receiver":
        data = await state.get_data()
        payer_id = data.get("pay_payer_member_id")
        if not payer_id:
            await callback.answer("Sessiya eskirgan. /pay qayta bosing.", show_alert=True)
            return
        if int(payer_id) == int(callback_data.member_id):
            await callback.answer("Payer va receiver bir xil bo'lmasin.", show_alert=True)
            return
        await state.update_data(pay_receiver_member_id=callback_data.member_id, pay_amount_k_str="")
        payer = next((m for m in members if m.id == int(payer_id)), None)
        receiver = next((m for m in members if m.id == int(callback_data.member_id)), None)
        await callback.message.edit_text(
            "<b>PAY</b>\n"
            f"Payer: <b>{member_label(payer) if payer else payer_id}</b>\n"
            f"Receiver: <b>{member_label(receiver) if receiver else callback_data.member_id}</b>\n\n"
            "Summa (k) kiriting:",
            parse_mode=ParseMode.HTML,
            reply_markup=numeric_keyboard(initiator_user_id=callback.from_user.id, field="pay_amount_k"),
        )
        await callback.answer()
        return


@router.callback_query(DigitCb.filter())
async def pay_digit_cb(callback: CallbackQuery, callback_data: DigitCb, state: FSMContext) -> None:
    if callback_data.field != "pay_amount_k":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    s = str(data.get("pay_amount_k_str") or "")
    if len(s) >= 7:
        await callback.answer("Juda katta summa.")
        return
    s = (s + str(callback_data.digit)).lstrip("0")
    await state.update_data(pay_amount_k_str=s)
    await callback.message.edit_text(
        "<b>PAY</b>\n"
        f"Summa (k): <b>{(s or '0')}k</b>\n\n"
        "Summani tugmalar bilan kiriting.",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=callback.from_user.id, field="pay_amount_k"),
    )
    await callback.answer()


@router.callback_query(NumActionCb.filter())
async def pay_num_action_cb(callback: CallbackQuery, callback_data: NumActionCb, session: AsyncSession, chat_db: Chat, state: FSMContext) -> None:
    if callback_data.field != "pay_amount_k":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    s = str(data.get("pay_amount_k_str") or "")
    if callback_data.action == "back":
        s = s[:-1]
        await state.update_data(pay_amount_k_str=s)
    elif callback_data.action == "clear":
        s = ""
        await state.update_data(pay_amount_k_str=s)
    elif callback_data.action == "ok":
        if not s:
            await callback.answer("Summani kiriting.", show_alert=True)
            return
        amount_k = int(s)
        if amount_k <= 0:
            await callback.answer("Summani to'g'ri kiriting.", show_alert=True)
            return
        payer_id = data.get("pay_payer_member_id")
        receiver_id = data.get("pay_receiver_member_id")
        if not payer_id or not receiver_id:
            await callback.answer("Sessiya eskirgan. /pay qayta bosing.", show_alert=True)
            return
        members = await list_members(session, chat_id=chat_db.id)
        payer = next((m for m in members if m.id == int(payer_id)), None)
        receiver = next((m for m in members if m.id == int(receiver_id)), None)
        await state.update_data(pay_amount_k=amount_k)
        await callback.message.edit_text(
            "<b>PAY</b>\n"
            f"Payer: <b>{member_label(payer) if payer else payer_id}</b>\n"
            f"Receiver: <b>{member_label(receiver) if receiver else receiver_id}</b>\n"
            f"Summa: <b>{amount_k}k</b>\n\n"
            "Tasdiqlaysizmi?",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_keyboard(initiator_user_id=callback.from_user.id, flow="pay"),
        )
        await callback.answer()
        return
    else:
        return

    await callback.message.edit_text(
        "<b>PAY</b>\n"
        f"Summa (k): <b>{(s or '0')}k</b>\n\n"
        "Summani tugmalar bilan kiriting.",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=callback.from_user.id, field="pay_amount_k"),
    )
    await callback.answer()


@router.callback_query(ConfirmCb.filter())
async def pay_confirm_cb(
    callback: CallbackQuery,
    callback_data: ConfirmCb,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
    state: FSMContext,
    dashboard: DashboardManager,
) -> None:
    if callback_data.flow != "pay":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    payer_id = data.get("pay_payer_member_id")
    receiver_id = data.get("pay_receiver_member_id")
    amount_k = int(data.get("pay_amount_k") or 0)
    if not payer_id or not receiver_id or amount_k <= 0:
        await callback.answer("Sessiya eskirgan. /pay qayta bosing.", show_alert=True)
        return
    try:
        # Receiver is stored as a single participant; ledger math matches transfer rule.
        await create_transaction(
            session,
            chat_id=chat_db.id,
            type=TransactionType.TRANSFER,
            amount_k=amount_k,
            paid_by_member_id=int(payer_id),
            participant_member_ids=[int(receiver_id)],
            note=None,
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    if callback.message:
        await safe_delete_message(bot, chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await state.clear()
    dashboard.schedule(callback.message.chat.id)
    await callback.answer("Saqlandi.")

