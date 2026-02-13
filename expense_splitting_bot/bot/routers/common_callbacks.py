from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from expense_splitting_bot.bot.callbacks import CloseCb, NumActionCb
from expense_splitting_bot.bot.utils import safe_delete_message

router = Router(name=__name__)


@router.callback_query(CloseCb.filter())
async def close_cb(callback: CallbackQuery, callback_data: CloseCb) -> None:
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    if callback.message:
        await safe_delete_message(callback.bot, chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await callback.answer()


@router.callback_query(NumActionCb.filter())
async def cancel_generic_cb(callback: CallbackQuery, callback_data: NumActionCb, state: FSMContext) -> None:
    # Used as a generic "Bekor qilish" in various keyboards.
    if callback_data.action != "cancel":
        return
    if callback.from_user.id != callback_data.initiator:
        await callback.answer("Bu tugma siz uchun emas.", show_alert=True)
        return
    if callback.message:
        await safe_delete_message(callback.bot, chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await state.clear()
    await callback.answer("Bekor qilindi.")
