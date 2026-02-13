from __future__ import annotations

from expense_splitting_bot.services.ledger import BalanceEntry, Transfer, compute_settlement


def example_integer_split_remainder_k() -> None:
    """
    amount_k is in thousands of UZS (k).

    Integer split:
      share_k = amount_k // n
      remainder = amount_k % n
      +1k distributed to first N participants ordered by tg_user_id.
    """

    amount_k = 403
    participants_tg_user_id_order = [10, 20, 30, 40]
    n = len(participants_tg_user_id_order)
    share_k = amount_k // n  # 100
    remainder = amount_k % n  # 3

    shares = []
    for i in range(n):
        shares.append(share_k + (1 if i < remainder else 0))

    assert shares == [101, 101, 101, 100]


def example_settlement_k() -> None:
    """
    Balance sign:
      positive -> owes
      negative -> is owed
    """

    entries = [
        BalanceEntry(member_id=1, balance_k=70),
        BalanceEntry(member_id=2, balance_k=30),
        BalanceEntry(member_id=3, balance_k=-100),
    ]
    transfers = compute_settlement(entries)
    assert transfers == [
        Transfer(from_member_id=1, to_member_id=3, amount_k=70),
        Transfer(from_member_id=2, to_member_id=3, amount_k=30),
    ]

