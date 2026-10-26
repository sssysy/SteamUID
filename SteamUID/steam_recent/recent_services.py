"""steam 最近游玩：拉取近两周游玩记录，按近两周时长降序出图。"""

import asyncio
from collections.abc import Sequence

from gsuid_core.logger import logger
from gsuid_core.ai_core.trigger_bridge import ai_return

from ..steam_config import SteamConfig
from ..utils.api.models import RecentlyPlayedGame
from ..utils.helper.config import region_cc, region_lang, griddb_cover_key
from ..utils.helper.profile import load_profile_assets, load_card_background_name
from ..utils.helper.ranking import format_duration
from ..utils.helper.steam_api import fetch_recently_played_games
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.game_detail import resolve_game_names, preferred_game_names
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.game_ranking import GameRankingEntry, render_game_ranking
from ..utils.render.html.static_assets import get_img_cache_url, resolve_card_bg_url, get_default_avatar_url

_TAG = "[Steam·最近游玩]"
_MINUTE_SECONDS = 60
# 单卡最多渲染的行数，超出按近两周时长截断
_MAX_ROWS = 50


def _ranked(games: Sequence[RecentlyPlayedGame]) -> list[tuple[str, int, str]]:
    """过滤零时长后按近两周分钟数降序截断，返回 (appid, 分钟, 接口名)。"""
    rows: list[tuple[str, int, str]] = []
    for game in games:
        if "appid" not in game:
            continue
        minutes = game["playtime_2weeks"] if "playtime_2weeks" in game else 0
        if minutes <= 0:
            continue
        rows.append((str(game["appid"]), minutes, game["name"] if "name" in game else ""))
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows[:_MAX_ROWS]


async def _game_entries(ranked: Sequence[tuple[str, int, str]]) -> list[GameRankingEntry]:
    """按传入顺序批量解析游戏名与封面，组装成排行行。"""
    appids = [appid for appid, _, _ in ranked]
    country = region_cc()
    griddb_key = griddb_cover_key()
    covers, names = await asyncio.gather(
        resolve_cover_names(appids, country=country, lang=region_lang(), griddb_key=griddb_key),
        resolve_game_names(appids, cc=country, lang=region_lang()),
    )
    names = await preferred_game_names(
        appids,
        fallbacks={appid: names[appid] if appid in names else api_name for appid, _, api_name in ranked},
        lang=region_lang(),
    )

    return [
        GameRankingEntry(
            appid=appid,
            name=names[appid] if appid in names else (api_name or appid),
            cover_url=get_img_cache_url(covers[appid]) if appid in covers else "",
            duration_seconds=minutes * _MINUTE_SECONDS,
        )
        for appid, minutes, api_name in ranked
    ]


async def _account_pill(steamid64: str) -> PillAccount | None:
    """右上角账号胶囊；资料抓取失败时跳过胶囊，不影响排行本体。"""
    loaded = await asyncio.gather(load_profile_assets(steamid64), return_exceptions=True)
    profile = loaded[0]
    if isinstance(profile, BaseException):
        logger.warning(f"{_TAG} 胶囊资料获取失败 {steamid64}: {profile!r}")
        return None
    return PillAccount(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=get_img_cache_url(profile.background_name),
    )


def _ai_return_recent_play(entries: Sequence[GameRankingEntry]) -> None:
    """把已解析的最近游玩记录以文本交给 AI。"""
    lines = ["[Steam] 最近两周游玩记录："]
    for index, entry in enumerate(entries, 1):
        lines.append(f"{index}. {entry.name} (AppID {entry.appid})：{format_duration(entry.duration_seconds)}")
    ai_return("\n".join(lines))


async def build_recent_play(steamid64: str) -> bytes:
    """出图入口：拉近两周游玩记录 -> 排序截断 -> 解析名字与封面 -> 渲染。"""
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")

    payload = await fetch_recently_played_games(
        steamid64,
        keys=keys,
        cooldown=SteamConfig.get_config("KeyPoolCooldown").data,
    )
    games = payload["games"] if "games" in payload else []
    ranked = _ranked(games)
    if not ranked:
        raise ValueError("该账号最近两周没有游玩记录")

    entries = await _game_entries(ranked)
    _ai_return_recent_play(entries)
    account, card_bg_name = await asyncio.gather(
        _account_pill(steamid64),
        load_card_background_name(steamid64),
    )
    return await render_game_ranking(
        f"steam最近两周游玩 Top{len(entries)}",
        entries,
        account,
        card_bg_url=resolve_card_bg_url(card_bg_name),
        duration_header="近两周时长",
    )
