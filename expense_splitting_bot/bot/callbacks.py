from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class CloseCb(CallbackData, prefix="close"):
    initiator: int


class DigitCb(CallbackData, prefix="digit"):
    initiator: int
    field: str  # "amount_k"
    digit: int


class NumActionCb(CallbackData, prefix="numact"):
    initiator: int
    field: str  # "amount_k"
    action: str  # ok | back | clear | cancel


class PickMemberCb(CallbackData, prefix="pickm"):
    initiator: int
    field: str  # paid_by | payer | receiver
    member_id: int


class PageCb(CallbackData, prefix="page"):
    initiator: int
    flow: str  # setup | room_payer | split_payer | split_participants | pay_payer | pay_receiver
    page: int


class SetupToggleResidentCb(CallbackData, prefix="setup_res"):
    initiator: int
    member_id: int
    page: int


class SetupDoneCb(CallbackData, prefix="setup_done"):
    initiator: int


class ToggleParticipantCb(CallbackData, prefix="tpart"):
    initiator: int
    member_id: int


class SplitParticipantsActionCb(CallbackData, prefix="spact"):
    initiator: int
    action: str  # done | all | clear


class ConfirmCb(CallbackData, prefix="confirm"):
    initiator: int
    flow: str  # room | split | pay

