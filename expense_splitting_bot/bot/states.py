from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SetupFlow(StatesGroup):
    wizard_message_id = State()
    page = State()


class RoomFlow(StatesGroup):
    wizard_message_id = State()
    amount_k = State()
    paid_by_member_id = State()


class SplitFlow(StatesGroup):
    wizard_message_id = State()
    amount_k = State()
    paid_by_member_id = State()
    participant_member_ids = State()
    note = State()


class PayFlow(StatesGroup):
    wizard_message_id = State()
    payer_member_id = State()
    receiver_member_id = State()
    amount_k = State()

