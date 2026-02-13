from __future__ import annotations

from expense_splitting_bot.db.models import Member


def member_label(m: Member) -> str:
    if m.username:
        return f"@{m.username}"
    if m.first_name:
        return m.first_name
    return str(m.tg_user_id)


def format_k(amount_k: int) -> str:
    # Uzbek-style: show "403k"
    sign = "+" if amount_k > 0 else ""
    return f"{sign}{amount_k}k"

