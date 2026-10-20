"""带密钥池的 Steam API 调用封装：分批、429 换 Key 与类型收窄。"""

import re
import time
from functools import partial
from collections.abc import Sequence

import msgspec

from .config import api_base
from ..key_pool import request_with_api_key
from ..api.models import (
    PlayerBan,
    FriendEntry,
    WishlistItem,
    PlayerSummary,
    OwnedGamesPayload,
    PlayerStatsPayload,
    AchievementSchemaEntry,
    RecentlyPlayedGamesPayload,
)
from ..api.public import (
    get_friend_list,
    get_owned_games,
    get_player_bans,
    get_user_wishlist,
    resolve_vanity_url,
    get_player_summaries,
    get_achievement_schema,
    get_player_achievements,
    get_recently_played_games,
    get_global_achievement_percentages,
)
from ..database.model_cache import SteamCache

# GetPlayerSummaries 单次请求的 steamid 上限，写死不再配置
SUMMARY_CHUNK = 50
_LANG = "schinese"
_SCHEMA_CACHE_TYPE = "achievement_schema"
_PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?")


async def _request_summaries(chunk: list[str], key: str) -> list[PlayerSummary]:
    return await get_player_summaries(chunk, key=key, base_url=api_base())


async def fetch_player_summaries(
    steamids: Sequence[str],
    *,
    keys: Sequence[str],
    cooldown: int,
) -> list[PlayerSummary]:
    """批量查询玩家摘要，按 50 个一批。"""
    ids = list(steamids)
    players: list[PlayerSummary] = []
    for start in range(0, len(ids), SUMMARY_CHUNK):
        chunk = ids[start : start + SUMMARY_CHUNK]
        players.extend(await request_with_api_key(partial(_request_summaries, chunk), keys, cooldown_seconds=cooldown))
    return players


async def _request_friend_list(steamid64: str, key: str) -> list[FriendEntry]:
    return await get_friend_list(steamid64, key=key, base_url=api_base())


async def fetch_friend_list(
    steamid64: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> list[FriendEntry]:
    """查询目标账号好友列表，429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_request_friend_list, steamid64),
        keys,
        cooldown_seconds=cooldown,
    )


async def _request_player_bans(steamid64: str, key: str) -> list[PlayerBan]:
    return await get_player_bans(steamid64, key=key, base_url=api_base())


async def fetch_player_bans(
    steamid64: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> list[PlayerBan]:
    """查询玩家封禁汇总，429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_request_player_bans, steamid64),
        keys,
        cooldown_seconds=cooldown,
    )


async def _request_owned_games(steamid64: str, key: str) -> OwnedGamesPayload:
    return await get_owned_games(steamid64, key=key, base_url=api_base())


async def fetch_owned_games(
    steamid64: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> OwnedGamesPayload:
    """查询玩家游戏库，429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_request_owned_games, steamid64),
        keys,
        cooldown_seconds=cooldown,
    )


async def _request_recently_played(steamid64: str, key: str) -> RecentlyPlayedGamesPayload:
    return await get_recently_played_games(steamid64, key=key, base_url=api_base())


async def fetch_recently_played_games(
    steamid64: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> RecentlyPlayedGamesPayload:
    """查询玩家近两周游玩记录，429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_request_recently_played, steamid64),
        keys,
        cooldown_seconds=cooldown,
    )


async def _request_wishlist(steamid64: str, key: str) -> list[WishlistItem]:
    return await get_user_wishlist(steamid64, key=key, base_url=api_base())


async def fetch_wishlist(
    steamid64: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> list[WishlistItem]:
    """查询玩家愿望单，429 由密钥池换 Key 重试。"""
    return await request_with_api_key(
        partial(_request_wishlist, steamid64),
        keys,
        cooldown_seconds=cooldown,
    )


async def _request_achievements(appid: str, steamid64: str, key: str) -> PlayerStatsPayload:
    return await get_player_achievements(appid, steamid64, key=key, lang=_LANG, base_url=api_base())


async def fetch_player_achievements(
    appid: str,
    steamid64: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> PlayerStatsPayload:
    return await request_with_api_key(
        partial(_request_achievements, appid, steamid64),
        keys,
        cooldown_seconds=cooldown,
    )


async def _request_schema(appid: str, key: str) -> list[AchievementSchemaEntry]:
    return await get_achievement_schema(appid, key=key, lang=_LANG, base_url=api_base())


async def fetch_achievement_schema(
    appid: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> list[AchievementSchemaEntry]:
    """取成就定义；命中持久缓存直接返回，未命中才走密钥池并回写。"""
    cached = await SteamCache.get_value(_SCHEMA_CACHE_TYPE, appid)
    if cached:
        return msgspec.json.decode(cached, type=list[AchievementSchemaEntry])

    entries = await request_with_api_key(partial(_request_schema, appid), keys, cooldown_seconds=cooldown)
    if entries:
        encoded = msgspec.json.encode(entries).decode("utf-8")
        await SteamCache.upsert(_SCHEMA_CACHE_TYPE, appid, encoded, int(time.time()))
    return entries


def _normalize_global_percent(raw: str) -> str:
    if _PERCENT_PATTERN.fullmatch(raw) is None:
        return ""
    value = float(raw)
    if value < 0 or value > 100:
        return ""
    return f"{value:.1f}"


async def fetch_global_achievement_percentages(appid: str) -> dict[str, str]:
    """查询并规范化全球成就百分比；单条非法值直接略过。"""
    entries = await get_global_achievement_percentages(appid, base_url=api_base())
    percentages: dict[str, str] = {}
    for entry in entries:
        if "name" not in entry or "percent" not in entry:
            continue
        percent = _normalize_global_percent(entry["percent"])
        if percent:
            percentages[entry["name"]] = percent
    return percentages


async def _request_vanity_steamid64(vanity: str, key: str) -> str | None:
    return await resolve_vanity_url(vanity, key=key, base_url=api_base())


async def fetch_vanity_steamid64(
    vanity: str,
    *,
    keys: Sequence[str],
    cooldown: int,
) -> str | None:
    """把个人资料页自定义域名换成 steamid64；不存在返回 None，429 换 Key 重试。"""
    return await request_with_api_key(
        partial(_request_vanity_steamid64, vanity),
        keys,
        cooldown_seconds=cooldown,
    )
