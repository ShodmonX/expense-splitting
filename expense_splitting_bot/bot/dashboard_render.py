from __future__ import annotations

import html
from datetime import datetime, timezone

from expense_splitting_bot.bot.text import format_k, member_label
from expense_splitting_bot.db.models import Member
from expense_splitting_bot.services.ledger import BalanceEntry, Transfer


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def render_dashboard(
    *,
    chat_title: str | None,
    residents: list[Member],
    room_total_k: int,
    balances: list[BalanceEntry],
    transfers: list[Transfer],
    members_by_id: dict[int, Member],
) -> str:
    title = f"🏠 Kvartira hisobi — {_esc(chat_title)}" if chat_title else "🏠 Kvartira hisobi"

    if residents:
        residents_txt = " ".join(_esc(member_label(m)) for m in residents)
    else:
        residents_txt = "<i>Hali tanlanmagan</i>"

    lines_bal: list[str] = []
    for b in balances[:12]:
        m = members_by_id.get(b.member_id)
        name = _esc(member_label(m)) if m else str(b.member_id)
        if b.balance_k < 0:
            lines_bal.append(f"{name:<12}  {format_k(b.balance_k)} (oladi)")
        elif b.balance_k > 0:
            lines_bal.append(f"{name:<12}  {format_k(b.balance_k)} (beradi)")
        else:
            lines_bal.append(f"{name:<12}  0k")

    if not lines_bal:
        lines_bal = ["Hali balans yo'q."]

    lines_settle: list[str] = []
    for t in transfers[:8]:
        frm = members_by_id.get(t.from_member_id)
        to = members_by_id.get(t.to_member_id)
        frm_txt = _esc(member_label(frm)) if frm else str(t.from_member_id)
        to_txt = _esc(member_label(to)) if to else str(t.to_member_id)
        lines_settle.append(f"{frm_txt} → {to_txt}: {t.amount_k}k")
    if not lines_settle:
        lines_settle = ["Hozircha kerak emas."]

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    text = (
        f"{title}\n\n"
        f"<b>Residents:</b>\n"
        f"{residents_txt}\n\n"
        f"<b>ROOM jami:</b> {room_total_k}k\n\n"
        f"<b>Balanslar:</b>\n"
        f"<pre>{_esc(chr(10).join(lines_bal))}</pre>\n"
        f"<b>Tavsiya etilgan to'lovlar:</b>\n"
        f"<pre>{_esc(chr(10).join(lines_settle))}</pre>\n"
        f"<i>Yangilandi: {updated}</i>"
    )
    return text[:4096]

