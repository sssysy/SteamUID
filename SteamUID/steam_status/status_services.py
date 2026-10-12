"""steam状态：汇总摘要 / 状态 / 装扮，渲染静态或动态迷你资料卡。"""

from ..steam_config import get_api_keys, get_key_cooldown
from ..utils.api.models import PlayerSummary
from ..utils.helper.bind import is_logged_in
from ..utils.helper.level import load_level_badge
from ..utils.helper.profile import load_status_assets
from ..utils.helper.steam_api import fetch_player_summaries
from ..utils.render.html.status_card import StatusCard, render_status_card
from ..utils.render.html.static_assets import (
    get_img_cache_url,
    get_default_avatar_url,
)

_LANG = "schinese"

# communityvisibilitystate 取 1 即资料私密
_VISIBILITY_PRIVATE = 1

# personastate -> 文案；0 为离线，未知取值视为在线
PERSONA_TEXT: dict[int, str] = {
    0: "离线",
    1: "在线",
    2: "忙碌",
    3: "离开",
    4: "打盹",
    5: "想交易",
    6: "想游玩",
}


def _presence(player: PlayerSummary) -> tuple[str, str]:
    """返回 (状态文案, 色调)；游戏中优先于在线状态。"""
    if "gameid" in player and player["gameid"]:
        title = player["gameextrainfo"] if "gameextrainfo" in player else ""
        return (f"游戏中：{title}" if title else "游戏中"), "in-game"

    state = player["personastate"] if "personastate" in player else 0
    text = PERSONA_TEXT[state] if state in PERSONA_TEXT else "在线"
    tone = "offline" if state == 0 else "online"
    return text, tone


def _is_private(player: PlayerSummary) -> bool:
    """资料是否私密；字段缺失按公开处理。"""
    if "communityvisibilitystate" not in player:
        return False
    return player["communityvisibilitystate"] == _VISIBILITY_PRIVATE


async def build_status_image(steamid64: str) -> bytes:
    """出图入口：摘要 → 私密校验 → 装扮素材 → 静态或动态渲染。"""
    keys = get_api_keys()
    if not keys:
        raise ValueError("请先配置 Steam API Key")
    cooldown = get_key_cooldown()

    players = await fetch_player_summaries([steamid64], keys=keys, cooldown=cooldown)
    if not players:
        raise ValueError("未找到该 Steam 用户")
    player = players[0]

    if _is_private(player) and not await is_logged_in(steamid64):
        raise ValueError("该用户资料为私有，无法查看状态")

    fallback_avatar = player["avatarfull"] if "avatarfull" in player else ""
    assets = await load_status_assets(
        steamid64,
        keys=keys,
        cooldown=cooldown,
        lang=_LANG,
        fallback_avatar_url=fallback_avatar,
    )
    badge = await load_level_badge(assets.level)
    status_text, status_tone = _presence(player)

    card = StatusCard(
        name=player["personaname"] if "personaname" in player else "",
        avatar_url=get_img_cache_url(assets.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(assets.frame_name),
        background_url=get_img_cache_url(assets.background_name),
        background_webm_url=get_img_cache_url(assets.background_webm_name),
        background_mp4_url=get_img_cache_url(assets.background_mp4_name),
        status_text=status_text,
        status_tone=status_tone,
        level=assets.level,
        level_border_color=badge.border_color,
        level_sprite_url=get_img_cache_url(badge.sprite_name),
        level_offset_px=badge.offset_px,
        badge_icon_url=get_img_cache_url(assets.badge_icon_name),
        badge_name=assets.badge_name,
        badge_xp=assets.badge_xp,
    )
    dynamic = bool(assets.animated_avatar_name or assets.background_webm_name or assets.background_mp4_name)
    return await render_status_card(card, dynamic=dynamic)
