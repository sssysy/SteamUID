"""Steam 榜单接口：周热销 / 当前在线 / 本周活跃三个榜单。

只发一次请求并原样返回结构，密钥轮换与筛选截断由调用方编排。
"""

import json

from .client import make_async_client, request_ok_response
from .models import (
    ChartsQuery,
    MostPlayedPayload,
    MostPlayedResponse,
    StoreBrowseContext,
    StoreItemDataRequest,
    WeeklyTopSellersQuery,
    WeeklyTopSellersPayload,
    ConcurrentPlayersPayload,
    WeeklyTopSellersResponse,
    ConcurrentPlayersResponse,
)
from .endpoints import (
    API_BASE_DEFAULT,
    API_GET_MOST_PLAYED_GAMES,
    API_GET_WEEKLY_TOP_SELLERS,
    API_GET_GAMES_BY_CONCURRENT_PLAYERS,
)

_TAG = "排行榜"


def _data_request() -> StoreItemDataRequest:
    """榜单条目申请简介 / 封面 / 单次购买价；折扣信息仍以商店详情为准。"""
    return {"include_basic_info": True, "include_assets": True, "include_all_purchase_options": True}


def _context(lang: str, country_code: str) -> StoreBrowseContext:
    return {"language": lang, "country_code": country_code}


def _params(key: str, query: WeeklyTopSellersQuery | ChartsQuery) -> dict[str, str]:
    """三个榜单接口只接受 GET + input_json，且必须带 key。"""
    return {"key": key, "input_json": json.dumps(query, ensure_ascii=False)}


async def get_weekly_top_sellers(
    *,
    key: str,
    lang: str,
    country_code: str,
    start_date: int | None = None,
    page_start: int = 0,
    page_count: int = 30,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> WeeklyTopSellersPayload:
    """周热销榜；start_date 传该周周二 0 点 UTC 秒，留空取最近一周。"""
    query: WeeklyTopSellersQuery = {
        "country_code": country_code,
        "context": _context(lang, country_code),
        "data_request": _data_request(),
        "page_start": page_start,
        "page_count": page_count,
    }
    if start_date is not None:
        query["start_date"] = start_date

    url = f"{base_url.rstrip('/')}{API_GET_WEEKLY_TOP_SELLERS}"
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=_params(key, query), timeout=timeout)

    payload: WeeklyTopSellersResponse = resp.json()
    return payload["response"]


async def get_games_by_concurrent_players(
    *,
    key: str,
    lang: str,
    country_code: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> ConcurrentPlayersPayload:
    """当前在线人数榜；榜单为全球口径，地区与语言只影响条目文案。"""
    query: ChartsQuery = {"context": _context(lang, country_code), "data_request": _data_request()}

    url = f"{base_url.rstrip('/')}{API_GET_GAMES_BY_CONCURRENT_PLAYERS}"
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=_params(key, query), timeout=timeout)

    payload: ConcurrentPlayersResponse = resp.json()
    return payload["response"]


async def get_most_played_games(
    *,
    key: str,
    lang: str,
    country_code: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> MostPlayedPayload:
    """本周活跃榜；接口按周汇总，rollup_date 为该周截止时间。"""
    query: ChartsQuery = {"context": _context(lang, country_code), "data_request": _data_request()}

    url = f"{base_url.rstrip('/')}{API_GET_MOST_PLAYED_GAMES}"
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=_params(key, query), timeout=timeout)

    payload: MostPlayedResponse = resp.json()
    return payload["response"]
