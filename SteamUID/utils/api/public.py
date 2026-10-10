"""Steam 公开 WebAPI 与商店页面接口。

每个函数只发一次请求并返回原始响应结构，缓存、批量分批与降级重试由调用方编排。
"""

from collections.abc import Sequence

from .client import STEAM_STORE_COOKIES, make_async_client, request_ok_response
from .models import (
    StoreEvent,
    WishlistItem,
    PlayerSummary,
    AppDetailsEntry,
    StoreSearchItem,
    WishlistResponse,
    OwnedGamesPayload,
    ServerInfoPayload,
    YearReviewPayload,
    MiniprofilePayload,
    OwnedGamesResponse,
    PlayerStatsPayload,
    ServerInfoResponse,
    YearReviewResponse,
    StoreSearchResponse,
    PartnerEventsResponse,
    SchemaForGameResponse,
    AchievementSchemaEntry,
    PlayerSummariesResponse,
    PlayerAchievementsResponse,
    ProfileItemsEquippedPayload,
    ProfileItemsEquippedResponse,
)
from .endpoints import (
    STORE_SEARCH,
    API_BASE_DEFAULT,
    API_GET_WISHLIST,
    STORE_BASE_DEFAULT,
    API_GET_OWNED_GAMES,
    API_GET_SERVER_INFO,
    COMMUNITY_MINIPROFILE,
    COMMUNITY_PROFILE_XML,
    COMMUNITY_BASE_DEFAULT,
    STORE_GET_GAME_DETAILS,
    API_GET_SCHEMA_FOR_GAME,
    API_GET_PLAYER_SUMMARIES,
    API_GET_PLAYER_ACHIEVEMENTS,
    STORE_EVENTS_PARTNER_PAGEABLE,
    API_GET_PROFILE_ITEMS_EQUIPPED,
    API_GET_USER_YEAR_IN_REVIEW_SHARE_IMAGE,
)

_TAG = "数据查询"
_STEAMID64_BASE = 76561197960265728


async def get_player_summaries(
    steamids: Sequence[str],
    *,
    key: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> list[PlayerSummary]:
    """查询玩家摘要，单次最多 50 个 steamid，分批由调用方负责。"""
    if not steamids:
        return []

    url = f"{base_url.rstrip('/')}{API_GET_PLAYER_SUMMARIES}"
    params = {"key": key, "steamids": ",".join(steamids)}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: PlayerSummariesResponse = resp.json()
    response = payload["response"]
    return response["players"] if "players" in response else []


async def get_game_details(
    appid: str,
    *,
    lang: str,
    cc: str | None = None,
    base_url: str = STORE_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> AppDetailsEntry:
    """查询单个游戏详情，cc 为空表示不带地区参数。"""
    url = f"{base_url.rstrip('/')}{STORE_GET_GAME_DETAILS}"
    params: dict[str, str] = {"appids": appid, "l": lang}
    if cc:
        params["cc"] = cc

    async with make_async_client(proxy=proxy, timeout=timeout, cookies=STEAM_STORE_COOKIES) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    body = resp.json()
    if not isinstance(body, dict):
        raise ValueError("游戏详情接口响应格式异常")
    entries: dict[str, AppDetailsEntry] = body
    if appid not in entries:
        raise ValueError(f"接口未返回 appid={appid} 的数据")
    return entries[appid]


async def get_price_overview(
    appids: Sequence[str],
    *,
    cc: str,
    base_url: str = STORE_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> dict[str, AppDetailsEntry]:
    """批量查询价格，只申请 price_overview 过滤字段；分批由调用方负责。"""
    if not appids:
        return {}

    url = f"{base_url.rstrip('/')}{STORE_GET_GAME_DETAILS}"
    params = {
        "appids": ",".join(appids),
        "cc": cc,
        "filters": "price_overview",
    }

    async with make_async_client(proxy=proxy, timeout=timeout, cookies=STEAM_STORE_COOKIES) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    body = resp.json()
    if not isinstance(body, dict):
        raise ValueError("游戏价格接口响应格式异常")
    entries: dict[str, AppDetailsEntry] = body
    return entries


async def get_owned_games(
    steamid: str,
    *,
    key: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> OwnedGamesPayload:
    """查询玩家游戏库，固定携带 appinfo / 免费游戏 / 扩展信息。"""
    url = f"{base_url.rstrip('/')}{API_GET_OWNED_GAMES}"
    params = {
        "key": key,
        "steamid": steamid,
        "include_appinfo": "1",
        "include_played_free_games": "1",
        "include_extended_appinfo": "1",
    }

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: OwnedGamesResponse = resp.json()
    return payload["response"]


async def get_player_achievements(
    appid: str,
    steamid: str,
    *,
    key: str,
    lang: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> PlayerStatsPayload:
    """查询玩家在指定游戏的成就进度。"""
    url = f"{base_url.rstrip('/')}{API_GET_PLAYER_ACHIEVEMENTS}"
    params = {"key": key, "appid": appid, "steamid": steamid, "l": lang}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: PlayerAchievementsResponse = resp.json()
    return payload["playerstats"]


async def get_achievement_schema(
    appid: str,
    *,
    key: str,
    lang: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> list[AchievementSchemaEntry]:
    """查询游戏成就定义（icon / 显示名 / 描述）。"""
    url = f"{base_url.rstrip('/')}{API_GET_SCHEMA_FOR_GAME}"
    params = {"key": key, "appid": appid, "l": lang}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: SchemaForGameResponse = resp.json()
    game = payload["game"]
    stats = game["availableGameStats"] if "availableGameStats" in game else {}
    return stats["achievements"] if "achievements" in stats else []


async def get_profile_items_equipped(
    steamid: str,
    *,
    key: str,
    lang: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 8.0,
) -> ProfileItemsEquippedPayload:
    """查询玩家装备的头像框 / 动画头像 / 背景等装扮项。"""
    url = f"{base_url.rstrip('/')}{API_GET_PROFILE_ITEMS_EQUIPPED}"
    params = {"key": key, "steamid": steamid, "l": lang}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: ProfileItemsEquippedResponse = resp.json()
    return payload["response"]


async def get_miniprofile(
    steamid64: str,
    *,
    lang: str,
    base_url: str = COMMUNITY_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> MiniprofilePayload:
    """查询社区 mini profile（等级 / 徽章 / 背景），URL 需要 steamid32。"""
    if not steamid64.isdigit():
        raise ValueError(f"无效的 steamid64: {steamid64}")

    steamid32 = int(steamid64) - _STEAMID64_BASE
    url = f"{base_url.rstrip('/')}{COMMUNITY_MINIPROFILE.format(steamid32=steamid32)}"

    async with make_async_client(proxy=proxy, timeout=timeout, headers={"Accept": "application/json"}) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params={"l": lang}, timeout=timeout)

    payload: MiniprofilePayload = resp.json()
    return payload


async def search_store(
    keyword: str,
    *,
    cc: str,
    lang: str,
    base_url: str = STORE_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> list[StoreSearchItem]:
    """按关键词检索商店候选，无结果时不自动切区，由调用方决定是否换 cc 重试。"""
    if not keyword.strip():
        return []

    url = f"{base_url.rstrip('/')}{STORE_SEARCH}"
    params = {"term": keyword, "l": lang, "cc": cc}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: StoreSearchResponse = resp.json()
    return payload["items"] if "items" in payload else []


async def get_game_announcements(
    appid: str,
    *,
    lang: str,
    count: int = 5,
    offset: int = 0,
    base_url: str = STORE_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> list[StoreEvent]:
    """拉取游戏官方公告原始事件列表，字段整理由调用方处理。"""
    url = f"{base_url.rstrip('/')}{STORE_EVENTS_PARTNER_PAGEABLE}"
    params = {
        "appid": appid,
        "clan_accountid": 0,
        "offset": offset,
        "count": count,
        "l": lang,
    }

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: PartnerEventsResponse = resp.json()
    return payload["events"] if "events" in payload else []


async def get_user_wishlist(
    steamid: str,
    *,
    key: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> list[WishlistItem]:
    """查询玩家愿望单原始条目，排序与凭据降级由调用方处理。"""
    url = f"{base_url.rstrip('/')}{API_GET_WISHLIST}"
    params = {"key": key, "steamid": steamid}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: WishlistResponse = resp.json()
    response = payload["response"]
    return response["items"] if "items" in response else []


async def get_year_in_review_share_images(
    steamid: str,
    year: int,
    *,
    language: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> YearReviewPayload:
    """查询年度回顾分享图原始响应，CDN 直链拼接由调用方处理。"""
    url = f"{base_url.rstrip('/')}{API_GET_USER_YEAR_IN_REVIEW_SHARE_IMAGE}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": STORE_BASE_DEFAULT,
        "Referer": f"{STORE_BASE_DEFAULT}/replay/{steamid}/{year}",
    }
    params = {"steamid": steamid, "year": year, "language": language}

    async with make_async_client(proxy=proxy, timeout=timeout, headers=headers, follow_redirects=True) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: YearReviewResponse = resp.json()
    return payload["response"]


async def get_community_profile_xml(
    steamid64: str,
    *,
    base_url: str = COMMUNITY_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 8.0,
) -> str:
    """取社区资料 XML 原文，XML 解析由调用方处理。"""
    url = f"{base_url.rstrip('/')}{COMMUNITY_PROFILE_XML.format(steamid64=steamid64)}"

    async with make_async_client(proxy=proxy, timeout=timeout, follow_redirects=True) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, timeout=timeout)

    return resp.text


async def get_server_info(
    *,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 5.0,
) -> ServerInfoPayload:
    """启动自检用的接口连通性探测。"""
    url = f"{base_url.rstrip('/')}{API_GET_SERVER_INFO}"

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, timeout=timeout)

    payload: ServerInfoResponse = resp.json()
    return payload["response"]
