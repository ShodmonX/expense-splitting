from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from expense_splitting_bot.bot.callbacks import (
    CloseCb,
    ConfirmCb,
    DigitCb,
    NumActionCb,
    PageCb,
    PickMemberCb,
    SetupDoneCb,
    SetupToggleResidentCb,
    SplitParticipantsActionCb,
    ToggleParticipantCb,
)
from expense_splitting_bot.db.models import Member
from expense_splitting_bot.bot.text import member_label


def close_keyboard(*, initiator_user_id: int, text: str = "Yopish") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text=text, callback_data=CloseCb(initiator=initiator_user_id).pack()),
        width=1,
    )
    return kb.as_markup()


def numeric_keyboard(*, initiator_user_id: int, field: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    digits = [
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
    ]
    for row in digits:
        kb.row(
            *[
                InlineKeyboardButton(
                    text=str(d),
                    callback_data=DigitCb(initiator=initiator_user_id, field=field, digit=d).pack(),
                )
                for d in row
            ],
            width=3,
        )
    kb.row(
        InlineKeyboardButton(text="0", callback_data=DigitCb(initiator=initiator_user_id, field=field, digit=0).pack()),
        InlineKeyboardButton(text="⬅️", callback_data=NumActionCb(initiator=initiator_user_id, field=field, action="back").pack()),
        InlineKeyboardButton(text="C", callback_data=NumActionCb(initiator=initiator_user_id, field=field, action="clear").pack()),
        width=3,
    )
    kb.row(
        InlineKeyboardButton(text="Bekor qilish", callback_data=NumActionCb(initiator=initiator_user_id, field=field, action="cancel").pack()),
        InlineKeyboardButton(text="OK", callback_data=NumActionCb(initiator=initiator_user_id, field=field, action="ok").pack()),
        width=2,
    )
    return kb.as_markup()


def members_keyboard(
    *,
    initiator_user_id: int,
    flow: str,
    field: str,
    members: list[Member],
    page: int,
    per_page: int = 8,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    start = page * per_page
    chunk = members[start : start + per_page]
    for m in chunk:
        kb.row(
            InlineKeyboardButton(
                text=member_label(m),
                callback_data=PickMemberCb(initiator=initiator_user_id, field=field, member_id=m.id).pack(),
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=PageCb(initiator=initiator_user_id, flow=flow, page=page - 1).pack(),
            )
        )
    if start + per_page < len(members):
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=PageCb(initiator=initiator_user_id, flow=flow, page=page + 1).pack(),
            )
        )
    if nav:
        kb.row(*nav, width=len(nav))
    kb.row(
        InlineKeyboardButton(text="Bekor qilish", callback_data=NumActionCb(initiator=initiator_user_id, field="wizard", action="cancel").pack()),
        width=1,
    )
    return kb.as_markup()


def setup_keyboard(
    *,
    initiator_user_id: int,
    members: list[Member],
    page: int,
    per_page: int = 8,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    start = page * per_page
    chunk = members[start : start + per_page]
    for m in chunk:
        prefix = "🏠" if m.is_resident else "➖"
        kb.row(
            InlineKeyboardButton(
                text=f"{prefix} {member_label(m)}",
                callback_data=SetupToggleResidentCb(initiator=initiator_user_id, member_id=m.id, page=page).pack(),
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=PageCb(initiator=initiator_user_id, flow="setup", page=page - 1).pack()))
    if start + per_page < len(members):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=PageCb(initiator=initiator_user_id, flow="setup", page=page + 1).pack()))
    if nav:
        kb.row(*nav, width=len(nav))

    kb.row(
        InlineKeyboardButton(text="Saqlash", callback_data=SetupDoneCb(initiator=initiator_user_id).pack()),
        InlineKeyboardButton(text="Bekor qilish", callback_data=NumActionCb(initiator=initiator_user_id, field="wizard", action="cancel").pack()),
        width=2,
    )
    return kb.as_markup()


def split_participants_keyboard(
    *,
    initiator_user_id: int,
    members: list[Member],
    selected_ids: set[int],
    page: int,
    per_page: int = 8,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    start = page * per_page
    chunk = members[start : start + per_page]
    for m in chunk:
        checked = "✅" if m.id in selected_ids else "☑️"
        kb.row(
            InlineKeyboardButton(
                text=f"{checked} {member_label(m)}",
                callback_data=ToggleParticipantCb(initiator=initiator_user_id, member_id=m.id).pack(),
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=PageCb(initiator=initiator_user_id, flow="split_participants", page=page - 1).pack()))
    if start + per_page < len(members):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=PageCb(initiator=initiator_user_id, flow="split_participants", page=page + 1).pack()))
    if nav:
        kb.row(*nav, width=len(nav))

    kb.row(
        InlineKeyboardButton(text="Hammasi", callback_data=SplitParticipantsActionCb(initiator=initiator_user_id, action="all").pack()),
        InlineKeyboardButton(text="Tozalash", callback_data=SplitParticipantsActionCb(initiator=initiator_user_id, action="clear").pack()),
        InlineKeyboardButton(text="Tayyor", callback_data=SplitParticipantsActionCb(initiator=initiator_user_id, action="done").pack()),
        width=3,
    )
    kb.row(
        InlineKeyboardButton(text="Bekor qilish", callback_data=NumActionCb(initiator=initiator_user_id, field="wizard", action="cancel").pack()),
        width=1,
    )
    return kb.as_markup()


def confirm_keyboard(*, initiator_user_id: int, flow: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Tasdiqlash", callback_data=ConfirmCb(initiator=initiator_user_id, flow=flow).pack()),
        InlineKeyboardButton(text="Bekor qilish", callback_data=NumActionCb(initiator=initiator_user_id, field="wizard", action="cancel").pack()),
        width=2,
    )
    return kb.as_markup()

