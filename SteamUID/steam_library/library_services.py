"""游戏墙与游戏推荐：拉取资料与游戏库、解析封面，最后渲染出图。"""

import random
import asyncio
from dataclasses import dataclass
from collections.abc import Sequence

from ..steam_config import SteamConfig
from ..utils.helper.config import region_cc, griddb_cover_key
from ..utils.helper.library import LibraryGame, visible_games
from ..utils.helper.profile import SteamProfile, load_profile_assets, load_card_background_name
from ..utils.helper.steam_api import fetch_owned_games
from ..utils.render.html.wall import WallGame, render_game_wall
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.game_detail import clean_description, load_store_detail
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.static_assets import get_img_cache_url, resolve_card_bg_url, get_default_avatar_url
from ..utils.render.html.game_recommend import RecommendGame, render_game_recommend

# 固定出 3 张；扫描上限与并发批避免大库无上限翻查商店详情
_RECOMMEND_COUNT = 3
_RECOMMEND_SCAN_LIMIT = 30
_RECOMMEND_BATCH = 10


@dataclass(frozen=True)
class _Candidate:
    """待出图的候选游戏；封面在选定之后再批量解析。"""

    appid: str
    name: str
    description: str


async def _load_profile_library(steamid64: str) -> tuple[SteamProfile, list[LibraryGame]]:
    """拉取资料与游戏库；API Key 缺失或游戏库不可见直接抛 ValueError。"""
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")

    profile = await load_profile_assets(steamid64)
    payload = await fetch_owned_games(steamid64, keys=keys, cooldown=SteamConfig.get_config("KeyPoolCooldown").data)
    if "games" not in payload:
        raise ValueError("未能获取该账号的游戏库，可能资料未公开或暂无游戏")

    library = [
        LibraryGame(
            appid=str(game["appid"]),
            name=game["name"] if "name" in game else "",
            playtime_minutes=(game["playtime_forever"] if "playtime_forever" in game else 0),
        )
        for game in payload["games"]
        if "appid" in game
    ]
    return profile, library


def _pill_account(profile: SteamProfile) -> PillAccount:
    """资料 -> 胶囊数据，图片字段统一转 img_cache 直链。"""
    return PillAccount(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=get_img_cache_url(profile.background_name),
    )


async def build_game_wall(steamid64: str) -> bytes:
    """出图入口：资料 -> 游戏库 -> 封面 -> 渲染。"""
    profile, library = await _load_profile_library(steamid64)

    played = visible_games(library)
    if not played:
        raise ValueError("该 steam 账号暂无可展示的游戏（需游玩时长 ≥ 10 分钟）")

    griddb_key = griddb_cover_key()
    covers = await resolve_cover_names(
        [game.appid for game in played],
        country=region_cc(),
        griddb_key=griddb_key,
    )

    wall_games = [
        WallGame(
            name=game.name,
            playtime_minutes=game.playtime_minutes,
            cover_url=get_img_cache_url(covers[game.appid]) if game.appid in covers else "",
        )
        for game in played
    ]
    return await render_game_wall(_pill_account(profile), wall_games)


async def _describe_candidate(appid: str) -> _Candidate | None:
    """取候选游戏的商店详情；无有效简介视为不可推荐，返回 None。"""
    entry = await load_store_detail(appid, None)
    if entry is None or "success" not in entry or not entry["success"]:
        return None
    if "data" not in entry:
        return None

    data = entry["data"]
    name = data["name"] if "name" in data else ""
    if not name:
        return None

    short = data["short_description"] if "short_description" in data else ""
    description = clean_description(short)
    if len(description) < 2:
        return None
    return _Candidate(appid=appid, name=name, description=description)


async def _pick_candidates(appids: Sequence[str]) -> list[_Candidate]:
    """按随机序并发扫描候选，凑够设定张数即停。"""
    picked: list[_Candidate] = []
    for start in range(0, len(appids), _RECOMMEND_BATCH):
        chunk = appids[start : start + _RECOMMEND_BATCH]
        results = await asyncio.gather(*(_describe_candidate(appid) for appid in chunk))
        for candidate in results:
            if candidate is None:
                continue
            picked.append(candidate)
            if len(picked) >= _RECOMMEND_COUNT:
                return picked
    return picked


async def build_recommend_pick(steamid64: str) -> bytes:
    """出图入口：随机打乱库内游戏 -> 商店详情筛简介 -> 解析封面 -> 渲染。"""
    profile, library = await _load_profile_library(steamid64)
    if not library:
        raise ValueError("该 steam 账号暂无游戏库存")

    appids = [game.appid for game in library]
    random.shuffle(appids)

    picked = await _pick_candidates(appids[:_RECOMMEND_SCAN_LIMIT])
    if not picked:
        raise ValueError("未能在游戏库中找到可推荐的有效游戏")

    griddb_key = griddb_cover_key()
    covers, card_bg_name = await asyncio.gather(
        resolve_cover_names(
            [candidate.appid for candidate in picked],
            country=region_cc(),
            griddb_key=griddb_key,
        ),
        load_card_background_name(steamid64),
    )
    games = [
        RecommendGame(
            name=candidate.name,
            description=candidate.description,
            cover_url=(get_img_cache_url(covers[candidate.appid]) if candidate.appid in covers else ""),
        )
        for candidate in picked
    ]
    return await render_game_recommend(
        _pill_account(profile),
        games,
        card_bg_url=resolve_card_bg_url(card_bg_name),
    )
