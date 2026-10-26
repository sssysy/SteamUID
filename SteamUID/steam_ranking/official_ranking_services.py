"""Steam 官方个人游戏时长排行：只读取当前用户主账号的游戏库。"""

import asyncio
from collections.abc import Sequence

from gsuid_core.models import Event

from ..steam_config import SteamConfig
from ..utils.api.models import OwnedGamesPayload
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.config import region_cc, region_lang, griddb_cover_key
from ..utils.helper.library import LibraryGame
from ..utils.helper.profile import SteamProfile, load_profile_assets, load_card_background_name
from ..utils.helper.steam_api import fetch_owned_games
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.game_detail import resolve_game_names, preferred_game_names
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.game_ranking import GameRankingEntry, render_game_ranking
from ..utils.render.html.static_assets import get_img_cache_url, resolve_card_bg_url, get_default_avatar_url

_DEFAULT_LIMIT = 10
_DURATION_HEADER = "官方累计时长"


def _limit_of(words: Sequence[str]) -> int:
    """首个参数为条数时取其值，否则回落默认 10。"""
    if words and words[0].isdigit() and int(words[0]) > 0:
        return int(words[0])
    return _DEFAULT_LIMIT


def _played_games(payload: OwnedGamesPayload) -> list[LibraryGame]:
    """把接口游戏库转为只含正时长的列表。"""
    if "games" not in payload:
        raise ValueError("未能获取该账号的游戏库，可能资料未公开或暂无游戏")

    games = [
        LibraryGame(
            appid=str(game["appid"]),
            name=game["name"] if "name" in game else "",
            playtime_minutes=game["playtime_forever"] if "playtime_forever" in game else 0,
        )
        for game in payload["games"]
        if "appid" in game
    ]
    return [game for game in games if game.playtime_minutes > 0]


def _account_pill(profile: SteamProfile) -> PillAccount:
    """资料 -> 胶囊数据，图片字段统一转 img_cache 直链。"""
    return PillAccount(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=get_img_cache_url(profile.background_name),
    )


async def _resolve_names(games: Sequence[LibraryGame], *, cc: str, lang: str) -> dict[str, str]:
    """只为接口未带名字的游戏补查名称。"""
    missing = [game.appid for game in games if not game.name]
    if not missing:
        return {}
    return await resolve_game_names(missing, cc=cc, lang=lang)


async def build_official_self_ranking(ev: Event) -> bytes:
    """steam排行[条数]：当前用户主账号的 Steam 官方游戏时长排行。"""
    steamid64 = await get_main_steamid64(ev, ev.user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")

    payload = await fetch_owned_games(
        steamid64,
        keys=keys,
        cooldown=SteamConfig.get_config("KeyPoolCooldown").data,
    )
    games = _played_games(payload)
    if not games:
        raise ValueError("该 Steam 账号暂无已游玩游戏数据")

    games.sort(key=lambda game: game.playtime_minutes, reverse=True)
    top_games = games[: _limit_of(ev.text.split())]
    country = region_cc()
    lang = region_lang()
    covers, names = await asyncio.gather(
        resolve_cover_names(
            [game.appid for game in top_games],
            country=country,
            lang=lang,
            griddb_key=griddb_cover_key(),
        ),
        _resolve_names(top_games, cc=country, lang=lang),
    )
    names = await preferred_game_names(
        [game.appid for game in top_games],
        fallbacks={
            game.appid: (names[game.appid] if game.appid in names and names[game.appid] else game.name or game.appid)
            for game in top_games
        },
        lang=lang,
    )
    profile, card_bg_name = await asyncio.gather(
        load_profile_assets(steamid64),
        load_card_background_name(steamid64),
    )
    entries = [
        GameRankingEntry(
            appid=game.appid,
            name=(names[game.appid] if game.appid in names and names[game.appid] else game.name or game.appid),
            cover_url=get_img_cache_url(covers[game.appid]) if game.appid in covers else "",
            duration_seconds=game.playtime_minutes * 60,
        )
        for game in top_games
    ]
    return await render_game_ranking(
        f"steam个人游戏时长排行 Top{len(entries)}",
        entries,
        _account_pill(profile),
        card_bg_url=resolve_card_bg_url(card_bg_name),
        duration_header=_DURATION_HEADER,
    )
