"""商店价格工具：实时批量取价、价格形态判定与价格文案格式化，不落盘、不留缓存。"""

import asyncio
from typing import Literal
from collections.abc import Sequence

from gsuid_core.logger import logger

from ..api.models import PriceOverview, AppDetailsData, AppDetailsEntry
from ..api.public import get_price_overview

_TAG = "[Steam·信息卡片]"

# 商店 appdetails 单请求上限约 800 个 appid（再多直接 400），500 留足余量
_PRICE_CHUNK = 500
_PRICE_CONCURRENCY = 5

# 售价形态：免费 / 折扣 / 标价 / 暂无（未发售或查不到价格）
PriceKind = Literal["free", "discount", "price", "unreleased"]


async def _chunk_value(appids: list[str], *, cc: str) -> int:
    """单批价格求和（分）；免费与无价条目没有 price_overview，直接不计入。"""
    entries = await get_price_overview(appids, cc=cc)
    total = 0
    for entry in entries.values():
        overview = price_overview(entry)
        if overview is None or "initial" not in overview:
            continue
        total += overview["initial"]
    return total


async def sum_library_value(appids: Sequence[str], *, cc: str) -> int | None:
    """按所选地区求和库内游戏原价（元）；任一批次失败返回 None 交给上层占位。"""
    chunks = [list(appids[start : start + _PRICE_CHUNK]) for start in range(0, len(appids), _PRICE_CHUNK)]
    if not chunks:
        return 0

    sem = asyncio.Semaphore(_PRICE_CONCURRENCY)

    async def _worker(chunk: list[str]) -> int:
        async with sem:
            return await _chunk_value(chunk, cc=cc)

    results = await asyncio.gather(*(_worker(chunk) for chunk in chunks), return_exceptions=True)
    total_cents = 0
    for result in results:
        if isinstance(result, BaseException):
            logger.warning(f"{_TAG} 价格批次失败: {result!r}")
            return None
        total_cents += result
    return round(total_cents / 100)


async def fetch_price_overviews(appids: Sequence[str], *, cc: str) -> dict[str, AppDetailsEntry]:
    """批量取价：按 500 分批并发，合并各批结果；单批失败只记日志、不拖垮整轮。"""
    chunks = [list(appids[start : start + _PRICE_CHUNK]) for start in range(0, len(appids), _PRICE_CHUNK)]
    if not chunks:
        return {}

    sem = asyncio.Semaphore(_PRICE_CONCURRENCY)

    async def _worker(chunk: list[str]) -> dict[str, AppDetailsEntry]:
        async with sem:
            return await get_price_overview(chunk, cc=cc)

    results = await asyncio.gather(*(_worker(chunk) for chunk in chunks), return_exceptions=True)
    merged: dict[str, AppDetailsEntry] = {}
    for result in results:
        if isinstance(result, BaseException):
            logger.warning(f"{_TAG} 价格批次失败: {result!r}")
            continue
        merged.update(result)
    return merged


def entry_data(entry: AppDetailsEntry | None) -> AppDetailsData | None:
    """成功响应里的 data；Steam 对无价条目会把 data 返回成 [] 或 null，先挡在字典访问前。"""
    if entry is None or "success" not in entry or not entry["success"] or "data" not in entry:
        return None
    data = entry["data"]
    if not isinstance(data, dict):
        return None
    return data


def price_overview(entry: AppDetailsEntry | None) -> PriceOverview | None:
    """实时批量价里的 price_overview；该 appid 没有价格数据时回落 None。"""
    data = entry_data(entry)
    if data is None or "price_overview" not in data:
        return None
    return data["price_overview"]


def price_fields(
    detail: AppDetailsData | None,
    overview: PriceOverview | None,
    *,
    currency: str,
) -> tuple[PriceKind, str, int]:
    """售价形态：免费 -> 即将推出 -> 折扣或标价 -> 暂无定价。"""
    if detail is not None and "is_free" in detail and detail["is_free"]:
        return "free", "免费", 0
    if detail is not None and "release_date" in detail:
        release = detail["release_date"]
        if "coming_soon" in release and release["coming_soon"]:
            return "unreleased", "即将推出", 0
    if overview is None:
        return "unreleased", "暂无定价", 0

    percent = overview["discount_percent"] if "discount_percent" in overview else 0
    text = format_price(overview, currency)
    if percent > 0:
        return "discount", text, percent
    return "price", text, 0


def format_price(overview: PriceOverview, currency: str) -> str:
    """价格文案：优先接口下发的本币格式化串，缺失时按货币符号与分值拼。"""
    formatted = overview["final_formatted"] if "final_formatted" in overview else ""
    if formatted:
        return formatted
    final = overview["final"] if "final" in overview else 0
    return f"{currency} {final / 100:.2f}"
