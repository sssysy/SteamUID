"""商店价格工具：实时批量取价求和与价格文案格式化，不落盘、不留缓存。"""

import asyncio
from collections.abc import Sequence

from gsuid_core.logger import logger

from ..api.models import PriceOverview
from ..api.public import get_price_overview

_TAG = "[Steam·信息卡片]"

# 商店 appdetails 单请求上限约 800 个 appid（再多直接 400），500 留足余量
_PRICE_CHUNK = 500
_PRICE_CONCURRENCY = 5


async def _chunk_value(appids: list[str], *, cc: str) -> int:
    """单批价格求和（分）；免费与无价条目只有空 data，需按非字典丢弃。"""
    entries = await get_price_overview(appids, cc=cc)
    total = 0
    for entry in entries.values():
        if "success" not in entry or not entry["success"]:
            continue
        if "data" not in entry:
            continue
        data = entry["data"]
        # Steam 对无价条目返回 [] 或 null，此处必须挡在字典访问之前
        if not isinstance(data, dict) or "price_overview" not in data:
            continue
        overview = data["price_overview"]
        if "initial" in overview:
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


def format_price(overview: PriceOverview, currency: str) -> str:
    """价格文案：优先接口下发的本币格式化串，缺失时按货币符号与分值拼。"""
    formatted = overview["final_formatted"] if "final_formatted" in overview else ""
    if formatted:
        return formatted
    final = overview["final"] if "final" in overview else 0
    return f"{currency} {final / 100:.2f}"
