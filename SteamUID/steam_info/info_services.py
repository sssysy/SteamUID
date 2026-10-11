"""steam 信息：汇总资料 / 状态 / 库存统计与实时价格，最后渲染出图。"""

import asyncio
import time

from ..steam_config import (
    get_api_keys,
    get_key_cooldown,
    get_region,
    get_region_cc,
)
from ..utils.api.models import OwnedGamesPayload, PlayerSummary
from ..utils.helper.level import load_level_badge
from ..utils.helper.price import sum_library_value
from ..utils.helper.profile import load_profile_assets
from ..utils.helper.steam_api import fetch_owned_games, fetch_player_summaries
from ..utils.maps import flag_emoji
from ..utils.render.html.info_card import InfoCard, render_info_card
from ..utils.render.html.static_assets import get_default_avatar_url, get_img_cache_url

_SECONDS_PER_YEAR = 31557600.0
_MINUTES_PER_HOUR = 60


def _presence(player: PlayerSummary) -> tuple[str, str]:
    """返回 (状态文案, 色调)；游戏中优先于在线状态。"""
    if "gameid" in player and player["gameid"]:
        title = player["gameextrainfo"] if "gameextrainfo" in player else ""
        return (f"游戏中：{title}" if title else "游戏中"), "ingame"
    state = player["personastate"] if "personastate" in player else 0
    if state != 0:
        return "在线", "online"
    return "离线", "offline"


def _account_age(timecreated: int) -> str:
    """注册年限，保留一位小数；注册时间未知返回空串。"""
    if timecreated <= 0:
        return ""
    return f"{(time.time() - timecreated) / _SECONDS_PER_YEAR:.1f}"


def _library_totals(payload: OwnedGamesPayload) -> tuple[int, int, list[str]]:
    """返回 (游戏数, 总时长分钟, appid 列表)，跳过无 appid 的异常条目。"""
    games = payload["games"] if "games" in payload else []
    total_minutes = 0
    appids: list[str] = []
    for game in games:
        if "appid" not in game:
            continue
        appids.append(str(game["appid"]))
        total_minutes += game["playtime_forever"] if "playtime_forever" in game else 0
    return len(appids), total_minutes, appids


async def build_steam_info(steamid64: str) -> bytes:
    """出图入口：资料 / 摘要 / 库存并发取回，再拼价格与等级后渲染。"""
    keys = get_api_keys()
    if not keys:
        raise ValueError("请先配置 Steam API Key")

    cooldown = get_key_cooldown()
    profile, players, library = await asyncio.gather(
        load_profile_assets(steamid64),
        fetch_player_summaries([steamid64], keys=keys, cooldown=cooldown),
        fetch_owned_games(steamid64, keys=keys, cooldown=cooldown),
    )
    if not players:
        raise ValueError("未找到该 Steam 用户")

    player = players[0]
    game_count, total_minutes, appids = _library_totals(library)
    account_value, badge = await asyncio.gather(
        sum_library_value(appids, cc=get_region_cc()),
        load_level_badge(profile.level),
    )
    status_text, status_tone = _presence(player)
    country = player["loccountrycode"] if "loccountrycode" in player else ""
    created = player["timecreated"] if "timecreated" in player else 0

    card = InfoCard(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=get_img_cache_url(profile.background_name),
        status_text=status_text,
        status_tone=status_tone,
        badge_icon_url=get_img_cache_url(profile.badge_icon_name),
        summary=profile.summary,
        level=profile.level,
        level_border_color=badge.border_color,
        level_sprite_url=get_img_cache_url(badge.sprite_name),
        level_offset_px=badge.offset_px,
        region=flag_emoji(country),
        account_age=_account_age(created),
        account_value=account_value,
        currency=get_region().currency,
        playtime_hours=total_minutes // _MINUTES_PER_HOUR,
        game_count=game_count,
    )
    return await render_info_card(card)
