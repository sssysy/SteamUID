"""Steam 玩家资料抓取：社区资料 XML + 迷你资料，素材经 downloader 落 img_cache。

只返回 img_cache 文件名，直链拼接由上层渲染层负责，避免 helper 反向依赖 render。
"""

import asyncio
from typing import Literal
from functools import partial
from xml.etree import ElementTree
from dataclasses import replace, dataclass
from collections.abc import Sequence

from gsuid_core.logger import logger

from .config import api_base, community_base
from .steamid import steamid64_to_friend_code
from ..key_pool import has_api_key, request_with_api_key
from ..api.models import (
    ProfileItemEntry,
    MiniprofilePayload,
    MiniprofileBackground,
    ProfileItemsEquippedPayload,
)
from ..api.public import (
    get_miniprofile,
    get_community_profile_xml,
    get_profile_items_equipped,
)
from ..downloader import download
from .game_detail import clean_description
from ...steam_config import SteamConfig
from ..api.endpoints import COMMUNITY_ASSETS_TEMPLATE

_TAG = "[Steam·账户绑定]"
_STATUS_TAG = "[Steam·用户状态]"
_LANG = "schinese"


@dataclass(frozen=True)
class SteamProfile:
    """玩家资料；图片字段为 img_cache 下的文件名，缺失为空串。"""

    steamid64: str
    name: str
    friend_code: str
    avatar_name: str
    frame_name: str
    background_name: str
    summary: str = ""
    level: int = 0
    badge_name: str = ""
    badge_icon_name: str = ""


@dataclass(frozen=True)
class _Decorations:
    """迷你资料里的装扮与等级，图片字段已落 img_cache。"""

    frame_name: str
    background_name: str
    level: int
    badge_name: str
    badge_icon_name: str


async def _download_name(url: str, *, force: bool = False) -> str:
    """下载素材到 img_cache，返回文件名；空 URL 或下载失败返回空串。

    视频背景同样落 img_cache，模板需以挂载直链引用。
    """
    if not url.strip():
        return ""
    path = await download(url, kind="image", force=force)
    return path.name if path is not None else ""


def _parse_profile_xml(xml: str) -> tuple[str, str, str]:
    """解析社区资料 XML，返回 (昵称, 头像原链, 简介)；不可见时抛 ValueError。"""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        raise ValueError("Steam 资料解析失败，请稍后重试") from e

    if root.find("error") is not None:
        raise ValueError("该 steamid 不存在或资料不可见")

    name = (root.findtext("steamID") or "").strip()
    avatar = (root.findtext("avatarFull") or root.findtext("avatarMedium")).strip()
    if not name and not avatar:
        raise ValueError("该 steamid 不存在或资料不可见")
    return name, avatar, clean_description(root.findtext("summary") or "")


async def _fetch_base_profile(steamid64: str, *, force: bool = False) -> SteamProfile:
    xml = await get_community_profile_xml(steamid64, base_url=community_base())
    name, avatar, summary = _parse_profile_xml(xml)
    return SteamProfile(
        steamid64=steamid64,
        name=name,
        friend_code=steamid64_to_friend_code(steamid64),
        avatar_name=await _download_name(avatar, force=force),
        frame_name="",
        background_name="",
        summary=summary,
    )


@dataclass(frozen=True)
class _MiniDeco:
    """迷你资料里的装扮原链与等级，尚未落盘。"""

    frame_url: str
    background_url: str
    background_webm_url: str
    background_mp4_url: str
    level: int
    badge_name: str
    badge_icon_url: str
    badge_xp: str


def _parse_miniprofile(payload: MiniprofilePayload) -> _MiniDeco:
    """从迷你资料解析装扮与等级；缺失字段统一回落到空串 / 0。"""
    frame = payload["avatar_frame"] if "avatar_frame" in payload else ""
    background = payload["profile_background"] if "profile_background" in payload else MiniprofileBackground()
    badge_name = ""
    badge_icon = ""
    badge_xp = ""
    if "favorite_badge" in payload:
        badge = payload["favorite_badge"]
        badge_name = badge["name"] if "name" in badge else ""
        badge_icon = badge["icon"] if "icon" in badge else ""
        xp = badge["xp"] if "xp" in badge else 0
        badge_xp = str(xp) if xp else ""
    return _MiniDeco(
        frame_url=frame,
        background_url=background["image"] if "image" in background else "",
        background_webm_url=(background["video/webm"] if "video/webm" in background else ""),
        background_mp4_url=(background["video/mp4"] if "video/mp4" in background else ""),
        level=payload["level"] if "level" in payload else 0,
        badge_name=badge_name,
        badge_icon_url=badge_icon,
        badge_xp=badge_xp,
    )


async def _fetch_decorations(steamid64: str, *, force: bool = False) -> _Decorations:
    """取头像框 / 背景 / 等级 / 特色徽章，返回已落盘的 img_cache 文件名。"""
    deco = _parse_miniprofile(await get_miniprofile(steamid64, lang=_LANG, base_url=community_base()))
    frame_name, background_name, badge_icon_name = await asyncio.gather(
        _download_name(deco.frame_url, force=force),
        _download_name(deco.background_url, force=force),
        _download_name(deco.badge_icon_url, force=force),
    )
    return _Decorations(
        frame_name=frame_name,
        background_name=background_name,
        level=deco.level,
        badge_name=deco.badge_name,
        badge_icon_name=badge_icon_name,
    )


async def load_profile_assets(steamid64: str, *, force: bool = False) -> SteamProfile:
    """抓取完整资料：昵称头像来自社区 XML，装扮来自迷你资料，背景优先装配项。

    任一来源失败只缺省对应字段，不影响昵称与头像；force 为真时重下图片。
    """
    base, decorations, background_name = await asyncio.gather(
        _fetch_base_profile(steamid64, force=force),
        _fetch_decorations(steamid64, force=force),
        _fetch_equipped_background(steamid64, force=force),
        return_exceptions=True,
    )
    if isinstance(base, BaseException):
        raise base

    if isinstance(decorations, BaseException):
        logger.warning(f"{_TAG} 迷你资料获取失败 {steamid64}: {decorations!r}")
        decorations = _Decorations(
            frame_name="",
            background_name="",
            level=0,
            badge_name="",
            badge_icon_name="",
        )

    if isinstance(background_name, BaseException):
        logger.warning(f"{_TAG} 个人资料背景获取失败 {steamid64}: {background_name!r}")
        background_name = ""

    return replace(
        base,
        frame_name=decorations.frame_name,
        # 个人资料背景优先，取不到时回落到迷你资料背景
        background_name=background_name or decorations.background_name,
        level=decorations.level,
        badge_name=decorations.badge_name,
        badge_icon_name=decorations.badge_icon_name,
    )


async def load_profile_background_name(steamid64: str) -> str:
    """取个人资料背景并落 img_cache；未装备时回落迷你资料背景，取不到返回空串。"""
    name = await _fetch_equipped_background(steamid64)
    if name:
        return name
    mini = await get_miniprofile(steamid64, lang=_LANG, base_url=community_base())
    deco = _parse_miniprofile(mini)
    return await _download_name(deco.background_url)


@dataclass(frozen=True)
class StatusAssets:
    """状态卡素材：图片与视频字段为 img_cache 下的文件名，缺失为空串。"""

    avatar_name: str
    animated_avatar_name: str
    frame_name: str
    background_name: str
    background_webm_name: str
    background_mp4_name: str
    level: int
    badge_name: str
    badge_icon_name: str
    badge_xp: str


def _community_asset_url(relative_path: str) -> str:
    """社区装扮相对路径转直链；空路径返回空串。"""
    if not relative_path.strip():
        return ""
    return COMMUNITY_ASSETS_TEMPLATE.format(path=relative_path)


async def _request_equipped(steamid64: str, lang: str, key: str) -> ProfileItemsEquippedPayload:
    return await get_profile_items_equipped(steamid64, key=key, lang=lang, base_url=api_base())


_EquippedKey = Literal["profile_background", "mini_profile_background"]


def _pick_equipped_item(
    payload: ProfileItemsEquippedPayload,
    key: _EquippedKey,
) -> ProfileItemEntry:
    """取装备项；未装备时返回空条目。"""
    if key in payload:
        return payload[key]
    return ProfileItemEntry()


def _item_large_url(item: ProfileItemEntry) -> str:
    """装备项大图（背景静态首帧）直链；无图返回空串。"""
    return _community_asset_url(item["image_large"] if "image_large" in item else "")


def _equipped_background_url(payload: ProfileItemsEquippedPayload) -> str:
    """个人资料背景直链；未装备时回落迷你资料背景，都没有返回空串。"""
    profile_bg = _item_large_url(_pick_equipped_item(payload, "profile_background"))
    if profile_bg:
        return profile_bg
    return _item_large_url(_pick_equipped_item(payload, "mini_profile_background"))


async def _fetch_equipped_background(steamid64: str, *, force: bool = False) -> str:
    """个人资料背景静态图落 img_cache；未配置 API Key 时返回空串。"""
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not has_api_key(keys):
        return ""
    payload = await request_with_api_key(
        partial(_request_equipped, steamid64, _LANG),
        keys,
        cooldown_seconds=SteamConfig.get_config("KeyPoolCooldown").data,
    )
    return await _download_name(_equipped_background_url(payload), force=force)


async def load_status_assets(
    steamid64: str,
    *,
    keys: Sequence[str],
    cooldown: int,
    lang: str = _LANG,
    fallback_avatar_url: str = "",
) -> StatusAssets:
    """取状态卡素材：迷你资料与装备项并发抓取，素材统一落 img_cache。

    fallback_avatar_url 用于装扮全部缺失时兜底摘要头像。
    """
    mini_raw, equipped_raw = await asyncio.gather(
        get_miniprofile(steamid64, lang=lang, base_url=community_base()),
        request_with_api_key(
            partial(_request_equipped, steamid64, lang),
            keys,
            cooldown_seconds=cooldown,
        ),
        return_exceptions=True,
    )
    if isinstance(mini_raw, BaseException):
        logger.warning(f"{_STATUS_TAG} 迷你资料获取失败 {steamid64}: {mini_raw!r}")
        mini = MiniprofilePayload()
    else:
        mini = mini_raw
    if isinstance(equipped_raw, BaseException):
        logger.warning(f"{_STATUS_TAG} 装备项获取失败 {steamid64}: {equipped_raw!r}")
        equipped = ProfileItemsEquippedPayload()
    else:
        equipped = equipped_raw

    deco = _parse_miniprofile(mini)
    animated = equipped["animated_avatar"] if "animated_avatar" in equipped else ProfileItemEntry()
    frame_item = equipped["avatar_frame"] if "avatar_frame" in equipped else ProfileItemEntry()

    animated_url = _community_asset_url(animated["image_small"] if "image_small" in animated else "")
    background_url = _equipped_background_url(equipped)
    frame_url = _community_asset_url(frame_item["image_small"] if "image_small" in frame_item else "") or deco.frame_url
    mini_avatar_url = mini["avatar_url"] if "avatar_url" in mini else ""

    avatar_name, frame_name, background_name, webm_name, mp4_name, badge_icon_name = await asyncio.gather(
        _download_name(animated_url or mini_avatar_url or fallback_avatar_url),
        _download_name(frame_url),
        _download_name(background_url or deco.background_url),
        _download_name(deco.background_webm_url),
        _download_name(deco.background_mp4_url),
        _download_name(deco.badge_icon_url),
    )
    return StatusAssets(
        avatar_name=avatar_name,
        # 装扮动图头像命中时 avatar_name 即动态素材，判定是否出 GIF 用
        animated_avatar_name=avatar_name if animated_url else "",
        frame_name=frame_name,
        background_name=background_name,
        background_webm_name=webm_name,
        background_mp4_name=mp4_name,
        level=deco.level,
        badge_name=deco.badge_name,
        badge_icon_name=badge_icon_name,
        badge_xp=deco.badge_xp,
    )
