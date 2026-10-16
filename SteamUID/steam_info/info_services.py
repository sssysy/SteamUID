"""steam 信息：汇总资料 / 状态 / 库存统计与实时价格，最后渲染出图。"""

import time
import asyncio

from ..utils.maps import flag_emoji
from ..steam_config import SteamConfig
from ..utils.api.models import PlayerSummary, OwnedGamesPayload
from ..utils.helper.level import load_level_badge
from ..utils.helper.price import sum_library_value
from ..utils.helper.config import region, region_cc, use_profile_card_bg
from ..utils.helper.command import resolve_steamid64
from ..utils.helper.profile import load_custom_url, load_profile_assets, load_card_background_name
from ..utils.helper.steamid import (
    steamid64_to_hex_id,
    steamid64_to_steamid3,
    steamid64_to_legacy_id,
    vanity_to_community_url,
    steamid64_to_friend_code,
    steamid64_to_community_url,
)
from ..utils.helper.steam_api import fetch_owned_games, fetch_player_summaries
from ..utils.render.html.info_card import InfoCard, render_info_card
from ..utils.render.html.static_assets import get_img_cache_url, get_default_avatar_url

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
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")

    cooldown = SteamConfig.get_config("KeyPoolCooldown").data
    profile, players, library, card_bg_name = await asyncio.gather(
        load_profile_assets(steamid64),
        fetch_player_summaries([steamid64], keys=keys, cooldown=cooldown),
        fetch_owned_games(steamid64, keys=keys, cooldown=cooldown),
        load_card_background_name(steamid64),
    )
    if not players:
        raise ValueError("未找到该 Steam 用户")

    player = players[0]
    game_count, total_minutes, appids = _library_totals(library)
    account_value, badge = await asyncio.gather(
        sum_library_value(appids, cc=region_cc()),
        load_level_badge(profile.level),
    )
    status_text, status_tone = _presence(player)
    country = player["loccountrycode"] if "loccountrycode" in player else ""
    created = player["timecreated"] if "timecreated" in player else 0

    # 开关开启时顶层底图只认个人资料背景，取不到交给模板回落自定义 / 默认底图
    if use_profile_card_bg():
        card_background = get_img_cache_url(card_bg_name)
    else:
        card_background = get_img_cache_url(profile.background_name)

    card = InfoCard(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=card_background,
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
        currency=region().currency,
        playtime_hours=total_minutes // _MINUTES_PER_HOUR,
        game_count=game_count,
    )
    return await render_info_card(card)


async def build_identity_text(raw: str) -> str:
    """把个人资料页 / steamid / 好友码转成多格式身份文本。"""
    text = raw.strip()
    if not text:
        raise ValueError("请传入个人资料页、steamid 或好友码")

    steamid64 = await resolve_steamid64(text)
    if steamid64 is None:
        raise ValueError("无法识别的输入，请传入个人资料页 / steamid / 好友码")

    custom_url = await load_custom_url(steamid64)
    lines = [
        "[Steam] 个人身份列表：",
        f"SteamID64: {steamid64}",
        f"SteamID64 (旧): {steamid64_to_legacy_id(steamid64)}",
        f"steamID3: {steamid64_to_steamid3(steamid64)}",
        f"SteamID32 (好友码): {steamid64_to_friend_code(steamid64)}",
        f"SteamHEXID: {steamid64_to_hex_id(steamid64)}",
    ]
    if custom_url:
        lines.append(f"Steam 自定社区 URL：{vanity_to_community_url(custom_url)}")
    lines.append(f"Steam 原始社区 URL：{steamid64_to_community_url(steamid64)}")
    return "\n".join(lines)
