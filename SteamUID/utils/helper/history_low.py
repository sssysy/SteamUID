"""史低缓存：地区键、接口结果转换与过期重试判断。"""

from typing import Literal, TypedDict

import msgspec

from ..api.models import AugmentedGamePrices

HISTORY_LOW_CACHE_TYPE = "steam_history_low"
HISTORY_LOW_RETRY_SECONDS = 24 * 60 * 60

HistoryLowStatus = Literal["ok", "missing"]


class HistoryLowCache(TypedDict):
    status: HistoryLowStatus
    lowest: int | None
    currency: str | None
    timestamp: str | None
    at_low_notified: bool
    checked_at: int


def history_low_key(appid: str, cc: str) -> str:
    return f"{appid}|{cc.strip().upper()}"


def missing_history_low(checked_at: int) -> HistoryLowCache:
    return HistoryLowCache(
        status="missing",
        lowest=None,
        currency=None,
        timestamp=None,
        at_low_notified=True,
        checked_at=checked_at,
    )


def history_low_from_game(game: AugmentedGamePrices | None, checked_at: int) -> HistoryLowCache:
    """接口结果转换成史低缓存；缺少史低字段时保留暂无状态。"""
    if game is None or "lowest" not in game or game["lowest"] is None:
        return missing_history_low(checked_at)
    lowest = game["lowest"]
    if "price" not in lowest:
        return missing_history_low(checked_at)
    price = lowest["price"]
    if "amountInt" not in price or "currency" not in price:
        return missing_history_low(checked_at)
    timestamp = lowest["timestamp"] if "timestamp" in lowest else None
    return HistoryLowCache(
        status="ok",
        lowest=price["amountInt"],
        currency=price["currency"],
        timestamp=timestamp,
        at_low_notified=True,
        checked_at=checked_at,
    )


def history_low_to_json(cache: HistoryLowCache) -> str:
    return msgspec.json.encode(cache).decode()


def history_low_from_json(raw: str) -> HistoryLowCache:
    return msgspec.json.decode(raw, type=HistoryLowCache)


def needs_history_low_refresh(cache: HistoryLowCache, now: int) -> bool:
    return cache["status"] == "missing" and now - cache["checked_at"] >= HISTORY_LOW_RETRY_SECONDS
