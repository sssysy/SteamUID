"""价格格式化与多数据源补价公共逻辑"""

from __future__ import annotations


def format_price(cents: int | float | None, currency: str) -> str:
    """把分格式化为带地区货币符号的价格字符串"""
    try:
        amount = (cents or 0) / 100
    except (TypeError, ValueError):
        amount = 0.0
    return f"{currency} {amount:.2f}"
