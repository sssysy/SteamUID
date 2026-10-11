"""带密钥池的 Steam API 调用封装：分批、429 换 Key 与类型收窄。"""

import time
from functools import partial
from collections.abc import Sequence

import msgspec

from ..api.models import (
    AchievementSchemaEntry,
    OwnedGamesPayload,
    PlayerStatsPayload,
    PlayerSummary,
)
from ..api.public import (
    get_owned_games,
    get_achievement_schema,
    get_player_achievements,
    get_player_summaries,
)
from ..database.model_cache import SteamCache
from ..key_pool import request_with_api_key

# GetPlayerSummaries 单次请求的 steamid 上限，写死不再配置
SUMMARY_CHUNK = 50
_LANG = "schinese"
_SCHEMA_CACHE_TYPE = "achievement_schema"


async def _request_summaries(chunk: list[str], key: str) -> list[PlayerSummary]:
    return await get_player_summaries(chunk, key=key)


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
        players.extend(
            await request_with_api_key(
                partial(_request_summaries, chunk), keys, cooldown_seconds=cooldown
            )
        )
    return players


async def _request_owned_games(steamid64: str, key: str) -> OwnedGamesPayload:
    return await get_owned_games(steamid64, key=key)


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


async def _request_achievements(
    appid: str, steamid64: str, key: str
) -> PlayerStatsPayload:
    return await get_player_achievements(appid, steamid64, key=key, lang=_LANG)


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
    return await get_achievement_schema(appid, key=key, lang=_LANG)


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

    entries = await request_with_api_key(
        partial(_request_schema, appid), keys, cooldown_seconds=cooldown
    )
    if entries:
        encoded = msgspec.json.encode(entries).decode("utf-8")
        await SteamCache.upsert(_SCHEMA_CACHE_TYPE, appid, encoded, int(time.time()))
    return entries
