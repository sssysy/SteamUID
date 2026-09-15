"""用户装扮资产（头像 / 头像框 / 背景 / 等级 / 徽章）与账号展示信息统一解析。"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from ..Api import (
    get_miniprofile,
    get_profile_items_equipped,
    get_user_Summaries,
)

# Steam 社区静态资源统一前缀
FASTLY_COMMUNITY_IMAGE_PREFIX = "https://shared.fastly.steamstatic.com/community_assets/images/"

_UNSET: Any = object()


@dataclass
class ProfileAssets:
    """统一的装扮资产解析结果。"""

    avatar_url: str = ""
    avatar_frame_url: str | None = None
    bg_url: str | None = None  # 静态背景图
    bg_video_webm: str | None = None  # 动态背景（仅 miniprofile 提供）
    bg_video_mp4: str | None = None
    level_num: str = "0"
    level_classes: str = "lvl_0"
    badge_icon_url: str | None = None
    badge_name: str | None = None
    badge_xp: str | None = None
    animated_avatar_url: str | None = None

    @property
    def has_bg_video(self) -> bool:
        return bool(self.bg_video_webm or self.bg_video_mp4)

    @property
    def has_animated_avatar(self) -> bool:
        """是否装备了动画头像 —— 数据里已经有这个信息，无需猜 URL 后缀。"""
        return bool(self.animated_avatar_url)


def _fastly_image(relative_path: str) -> str:
    return f"{FASTLY_COMMUNITY_IMAGE_PREFIX}{relative_path}"


def _parse_level(miniprofile_data: dict) -> tuple[str, str]:
    """从 miniprofile 解析等级数字与 CSS 类名（``friendPlayerLevel lvl_5`` → ``lvl_5``）。"""
    level = miniprofile_data.get("level", 0)
    level_num = str(level)
    level_classes = f"lvl_{level}" if level else "lvl_0"
    level_class = miniprofile_data.get("level_class", "")
    if level_class and "lvl_" in level_class:
        level_classes = level_class.replace("friendPlayerLevel", "").strip()
    return level_num, level_classes


async def resolve_profile_assets(
    steamid64: str,
    *,
    player: dict | None = None,
    miniprofile_data: Any = _UNSET,
    items_data: Any = _UNSET,
    include_animated: bool = False,
) -> ProfileAssets:
    """解析用户的装扮资产"""
    if miniprofile_data is _UNSET or items_data is _UNSET:
        mp_raw, items_raw = await asyncio.gather(
            get_miniprofile(steamid64),
            get_profile_items_equipped(steamid64),
            return_exceptions=True,
        )
        if miniprofile_data is _UNSET:
            miniprofile_data = mp_raw
        if items_data is _UNSET:
            items_data = items_raw

    mp: dict = miniprofile_data if isinstance(miniprofile_data, dict) else {}
    items: dict = items_data if isinstance(items_data, dict) else {}

    assets = ProfileAssets()

    # 动画头像（仅 GetProfileItemsEquipped 有）
    if include_animated:
        animated = items.get("animated_avatar") or {}
        if animated.get("image_small"):
            assets.animated_avatar_url = _fastly_image(animated["image_small"])

    # 头像：动画头像 > miniprofile 头像 > 摘要头像
    assets.avatar_url = (
        assets.animated_avatar_url
        or mp.get("avatar_url")
        or (player or {}).get("avatarfull", "")
    )

    # 头像框：GetProfileItemsEquipped 相对路径 > miniprofile 完整 URL > 不输出
    frame = items.get("avatar_frame") or {}
    if frame.get("image_small"):
        assets.avatar_frame_url = _fastly_image(frame["image_small"])
    elif mp.get("avatar_frame"):
        assets.avatar_frame_url = mp["avatar_frame"]

    # 背景：GetProfileItemsEquipped 静态图 > miniprofile 静态图 > 不输出；视频仅 miniprofile 有
    bg = mp.get("profile_background") or {}
    assets.bg_video_webm = bg.get("video/webm")
    assets.bg_video_mp4 = bg.get("video/mp4")
    mini_bg = items.get("mini_profile_background") or {}
    if mini_bg.get("image_large"):
        assets.bg_url = _fastly_image(mini_bg["image_large"])
    elif bg.get("image"):
        assets.bg_url = bg["image"]

    # 等级 / 特色徽章（仅 miniprofile 有）
    if mp:
        assets.level_num, assets.level_classes = _parse_level(mp)
        badge = mp.get("favorite_badge")
        if badge:
            assets.badge_icon_url = badge.get("icon")
            assets.badge_name = badge.get("name")
            assets.badge_xp = str(badge.get("xp", "")) if badge.get("xp") else None

    return assets


def calc_account_age(timecreated: int | None) -> str:
    """计算账号年限"""
    if not timecreated or not isinstance(timecreated, (int, float)) or timecreated <= 0:
        return "--"
    diff_sec = time.time() - float(timecreated)
    if diff_sec <= 0:
        return "0.0年"
    years = diff_sec / (365.25 * 86400)
    return f"{years:.1f}年"


async def get_account_display_name(steamid64: str) -> str:
    """获取账号展示昵称：本地缓存 → 登录账号名 → 在线摘要"""
    from ..database.models import SteamIDInfo, SteamNextAccount

    user_info_raw = await SteamIDInfo.get_steamuserinfo(steamid64)
    if user_info_raw:
        try:
            info = json.loads(user_info_raw)
            if isinstance(info, dict) and info.get("personaname"):
                return str(info["personaname"])
        except Exception:
            pass

    try:
        acc = await SteamNextAccount.get_account(steamid64)
        if acc and acc.account_name:
            return str(acc.account_name)
    except Exception:
        pass

    try:
        summaries = await get_user_Summaries(steamid64)
        if summaries and isinstance(summaries, list) and summaries[0].get("personaname"):
            return str(summaries[0]["personaname"])
    except Exception:
        pass

    return "Steam用户"


async def get_user_static_avatar_frame(steamid64: str) -> str | None:
    """获取用户的静态 Steam 头像框 URL"""
    assets = await resolve_profile_assets(steamid64)
    return assets.avatar_frame_url


async def get_user_pill_data(steamid64: str) -> dict:
    """构建药丸型卡片所需的用户数据字典"""
    from ..utils import steamid64_to_friend_code

    players_res, miniprofile_data, items_data = await asyncio.gather(
        get_user_Summaries(steamid64),
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        return_exceptions=True,
    )
    player = players_res[0] if (isinstance(players_res, list) and players_res) else {}

    assets = await resolve_profile_assets(
        steamid64,
        player=player,
        miniprofile_data=miniprofile_data,
        items_data=items_data,
    )

    return {
        "name": player.get("personaname", "未知用户"),
        "friend_code": steamid64_to_friend_code(steamid64),
        "avatar_url": assets.avatar_url,
        "avatar_frame_url": assets.avatar_frame_url,
        "bg_url": assets.bg_url,
    }
