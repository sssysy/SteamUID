"""榜单装载：经密钥池请求三个榜单接口，并把周起始时间往回换算。

只做请求编排，不筛选不落盘；取满条数与封面解析由调用方处理。
"""

from functools import partial
from collections.abc import Sequence

from .config import api_base
from ..key_pool import request_with_api_key
from ..api.charts import (
    get_most_played_games,
    get_weekly_top_sellers,
    get_games_by_concurrent_players,
)
from ..api.models import (
    MostPlayedPayload,
    WeeklyTopSellersPayload,
    ConcurrentPlayersPayload,
)

# 过滤非游戏后仍需取满 9 条，向后多取候选
PAGE_COUNT = 30
# 热销榜一周的跨度，用于把本周起始换算成上周起始
WEEK_SECONDS = 7 * 86400


async def _weekly(
    key: str,
    *,
    country_code: str,
    lang: str,
    start_date: int | None,
) -> WeeklyTopSellersPayload:
    return await get_weekly_top_sellers(
        key=key,
        lang=lang,
        country_code=country_code,
        start_date=start_date,
        page_count=PAGE_COUNT,
        base_url=api_base(),
    )


async def load_weekly_top_sellers(
    *,
    keys: Sequence[str],
    cooldown: int,
    country_code: str,
    lang: str,
    start_date: int | None = None,
) -> WeeklyTopSellersPayload:
    """周热销榜；429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_weekly, country_code=country_code, lang=lang, start_date=start_date),
        keys,
        cooldown_seconds=cooldown,
    )


async def _concurrent(key: str, *, country_code: str, lang: str) -> ConcurrentPlayersPayload:
    return await get_games_by_concurrent_players(
        key=key,
        lang=lang,
        country_code=country_code,
        base_url=api_base(),
    )


async def load_concurrent_players(
    *,
    keys: Sequence[str],
    cooldown: int,
    country_code: str,
    lang: str,
) -> ConcurrentPlayersPayload:
    """当前在线人数榜；429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_concurrent, country_code=country_code, lang=lang),
        keys,
        cooldown_seconds=cooldown,
    )


async def _most_played(key: str, *, country_code: str, lang: str) -> MostPlayedPayload:
    return await get_most_played_games(
        key=key,
        lang=lang,
        country_code=country_code,
        base_url=api_base(),
    )


async def load_most_played(
    *,
    keys: Sequence[str],
    cooldown: int,
    country_code: str,
    lang: str,
) -> MostPlayedPayload:
    """本周活跃榜；429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_most_played, country_code=country_code, lang=lang),
        keys,
        cooldown_seconds=cooldown,
    )


def previous_week_start(start_date: int) -> int:
    """热销榜上一周起始：接口按周发布，本周起始往前推一周即可。"""
    return start_date - WEEK_SECONDS
