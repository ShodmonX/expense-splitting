from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from expense_splitting_bot.bot.callbacks import ConfirmCb, DigitCb, NumActionCb, PageCb, PickMemberCb, SplitParticipantsActionCb, ToggleParticipantCb
from expense_splitting_bot.bot.dashboard import DashboardManager
from expense_splitting_bot.bot.keyboards import confirm_keyboard, members_keyboard, numeric_keyboard, split_participants_keyboard
from expense_splitting_bot.bot.utils import safe_delete_message
from expense_splitting_bot.db.models import Chat, TransactionType
from expense_splitting_bot.services.members import list_members
from expense_splitting_bot.services.transactions import create_transaction
from expense_splitting_bot.bot.text import member_label

router = Router(name=__name__)


def _require_group(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


@router.message(Command("split"))
async def split_cmd(message: Message, bot: Bot, session: AsyncSession, chat_db: Chat, state: FSMContext) -> None:
    if not _require_group(message):
        return
    await safe_delete_message(bot, chat_id=message.chat.id, message_id=message.message_id)
    await state.clear()
    await state.update_data(
        initiator_user_id=message.from_user.id,
        split_amount_k_str="",
        split_paid_by_member_id=None,
        split_participant_ids=[],
    )
    wizard = await message.answer(
        "<b>SPLIT (oddiy harajat)</b>\nSumma (k): <b>0k</b>\n\nSummani tugmalar bilan kiriting.",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=message.from_user.id, field="split_amount_k"),
    )
    await state.update_data(wizard_message_id=wizard.message_id)


@router.callback_query(DigitCb.filter())
async def split_digit_cb(callback: CallbackQuery, callback_data: DigitCb, state: FSMContext) -> None:
    if callback_data.field != "split_amount_k":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    s = str(data.get("split_amount_k_str") or "")
    if len(s) >= 7:
        await callback.answer("Juda katta summa.")
        return
    s = (s + str(callback_data.digit)).lstrip("0")
    await state.update_data(split_amount_k_str=s)
    await callback.message.edit_text(
        "<b>SPLIT</b>\n"
        f"Summa (k): <b>{(s or '0')}k</b>\n\n"
        "Summani tugmalar bilan kiriting.",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=callback.from_user.id, field="split_amount_k"),
    )
    await callback.answer()


@router.callback_query(NumActionCb.filter())
async def split_num_action_cb(
    callback: CallbackQuery,
    callback_data: NumActionCb,
    session: AsyncSession,
    chat_db: Chat,
    state: FSMContext,
) -> None:
    if callback_data.field != "split_amount_k":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return

    data = await state.get_data()
    s = str(data.get("split_amount_k_str") or "")

    if callback_data.action == "back":
        s = s[:-1]
        await state.update_data(split_amount_k_str=s)
    elif callback_data.action == "clear":
        s = ""
        await state.update_data(split_amount_k_str=s)
    elif callback_data.action == "ok":
        if not s:
            await callback.answer("Summani kiriting.", show_alert=True)
            return
        amount_k = int(s)
        if amount_k <= 0:
            await callback.answer("Summani to'g'ri kiriting.", show_alert=True)
            return
        members = await list_members(session, chat_id=chat_db.id)
        await state.update_data(split_amount_k=amount_k, split_payer_page=0)
        await callback.message.edit_text(
            "<b>SPLIT</b>\n"
            f"Summa: <b>{amount_k}k</b>\n\n"
            "Kim to'ladi?",
            parse_mode=ParseMode.HTML,
            reply_markup=members_keyboard(
                initiator_user_id=callback.from_user.id,
                flow="split_payer",
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
        "<b>SPLIT</b>\n"
        f"Summa (k): <b>{(s or '0')}k</b>\n\n"
        "Summani tugmalar bilan kiriting.",
        parse_mode=ParseMode.HTML,
        reply_markup=numeric_keyboard(initiator_user_id=callback.from_user.id, field="split_amount_k"),
    )
    await callback.answer()


@router.callback_query(PageCb.filter())
async def split_pages_cb(callback: CallbackQuery, callback_data: PageCb, session: AsyncSession, chat_db: Chat, state: FSMContext) -> None:
    if callback.from_user.id != callback_data.initiator:
        return
    if callback_data.flow == "split_payer":
        members = await list_members(session, chat_id=chat_db.id)
        await callback.message.edit_reply_markup(
            reply_markup=members_keyboard(
                initiator_user_id=callback.from_user.id,
                flow="split_payer",
                field="paid_by",
                members=members,
                page=callback_data.page,
            )
        )
        await callback.answer()
        return
    if callback_data.flow == "split_participants":
        data = await state.get_data()
        selected = set(int(x) for x in data.get("split_participant_ids", []))
        members = await list_members(session, chat_id=chat_db.id)
        await state.update_data(split_participants_page=callback_data.page)
        await callback.message.edit_reply_markup(
            reply_markup=split_participants_keyboard(
                initiator_user_id=callback.from_user.id,
                members=members,
                selected_ids=selected,
                page=callback_data.page,
            )
        )
        await callback.answer()
        return


@router.callback_query(PickMemberCb.filter())
async def split_pick_payer_cb(
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
    amount_k = int(data.get("split_amount_k") or 0)
    if amount_k <= 0:
        await callback.answer("Sessiya eskirgan. /split qayta bosing.", show_alert=True)
        return

    members = await list_members(session, chat_id=chat_db.id)
    payer = next((m for m in members if m.id == callback_data.member_id), None)
    await state.update_data(split_paid_by_member_id=callback_data.member_id, split_participant_ids=[m.id for m in members], split_participants_page=0)

    await callback.message.edit_text(
        "<b>SPLIT</b>\n"
        f"Summa: <b>{amount_k}k</b>\n"
        f"To'lovchi: <b>{member_label(payer) if payer else callback_data.member_id}</b>\n\n"
        "Ishtirokchilarni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=split_participants_keyboard(
            initiator_user_id=callback.from_user.id,
            members=members,
            selected_ids=set(m.id for m in members),
            page=0,
        ),
    )
    await callback.answer()


@router.callback_query(ToggleParticipantCb.filter())
async def split_toggle_participant_cb(callback: CallbackQuery, callback_data: ToggleParticipantCb, session: AsyncSession, chat_db: Chat, state: FSMContext) -> None:
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    selected = set(int(x) for x in data.get("split_participant_ids", []))
    if callback_data.member_id in selected:
        selected.remove(callback_data.member_id)
    else:
        selected.add(callback_data.member_id)
    await state.update_data(split_participant_ids=list(selected))
    page = int(data.get("split_participants_page") or 0)
    members = await list_members(session, chat_id=chat_db.id)
    await callback.message.edit_reply_markup(
        reply_markup=split_participants_keyboard(
            initiator_user_id=callback.from_user.id,
            members=members,
            selected_ids=selected,
            page=page,
        )
    )
    await callback.answer()


@router.callback_query(SplitParticipantsActionCb.filter())
async def split_participants_action_cb(
    callback: CallbackQuery,
    callback_data: SplitParticipantsActionCb,
    session: AsyncSession,
    chat_db: Chat,
    state: FSMContext,
) -> None:
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    amount_k = int(data.get("split_amount_k") or 0)
    paid_by_member_id = data.get("split_paid_by_member_id")
    if amount_k <= 0 or not paid_by_member_id:
        await callback.answer("Sessiya eskirgan. /split qayta bosing.", show_alert=True)
        return

    members = await list_members(session, chat_id=chat_db.id)
    if callback_data.action == "all":
        selected = {m.id for m in members}
        await state.update_data(split_participant_ids=list(selected))
        await callback.message.edit_reply_markup(
            reply_markup=split_participants_keyboard(
                initiator_user_id=callback.from_user.id,
                members=members,
                selected_ids=selected,
                page=int(data.get("split_participants_page") or 0),
            )
        )
        await callback.answer("Tanlandi.")
        return
    if callback_data.action == "clear":
        await state.update_data(split_participant_ids=[])
        await callback.message.edit_reply_markup(
            reply_markup=split_participants_keyboard(
                initiator_user_id=callback.from_user.id,
                members=members,
                selected_ids=set(),
                page=int(data.get("split_participants_page") or 0),
            )
        )
        await callback.answer("Tozalandi.")
        return
    if callback_data.action == "done":
        selected = set(int(x) for x in data.get("split_participant_ids", []))
        if not selected:
            await callback.answer("Kamida 1 ishtirokchi tanlang.", show_alert=True)
            return
        payer = next((m for m in members if m.id == int(paid_by_member_id)), None)
        await callback.message.edit_text(
            "<b>SPLIT</b>\n"
            f"Summa: <b>{amount_k}k</b>\n"
            f"To'lovchi: <b>{member_label(payer) if payer else paid_by_member_id}</b>\n"
            f"Ishtirokchilar: <b>{len(selected)}</b>\n\n"
            "Tasdiqlaysizmi?",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_keyboard(initiator_user_id=callback.from_user.id, flow="split"),
        )
        await callback.answer()
        return


@router.callback_query(ConfirmCb.filter())
async def split_confirm_cb(
    callback: CallbackQuery,
    callback_data: ConfirmCb,
    bot: Bot,
    session: AsyncSession,
    chat_db: Chat,
    state: FSMContext,
    dashboard: DashboardManager,
) -> None:
    if callback_data.flow != "split":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    data = await state.get_data()
    amount_k = int(data.get("split_amount_k") or 0)
    paid_by_member_id = data.get("split_paid_by_member_id")
    participant_ids = [int(x) for x in data.get("split_participant_ids", [])]
    if amount_k <= 0 or not paid_by_member_id or not participant_ids:
        await callback.answer("Sessiya eskirgan. /split qayta bosing.", show_alert=True)
        return
    try:
        await create_transaction(
            session,
            chat_id=chat_db.id,
            type=TransactionType.SPLIT,
            amount_k=amount_k,
            paid_by_member_id=int(paid_by_member_id),
            participant_member_ids=participant_ids,
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
