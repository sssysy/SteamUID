"""Steam 玩家资料抓取：社区资料 XML + 迷你资料，素材经 downloader 落 img_cache。

只返回 img_cache 文件名，直链拼接由上层渲染层负责，避免 helper 反向依赖 render。
装扮直链按 steamid 缓存在 SteamCache，命中后不再请求接口。
"""

import time
import asyncio
from typing import Literal, TypedDict
from functools import partial
from xml.etree import ElementTree
from dataclasses import replace, dataclass

import msgspec

from gsuid_core.logger import logger
from gsuid_core.models import Event

from .bind import get_main_steamid64
from .config import api_base, community_base, use_profile_card_bg
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
from ..database.model_cache import SteamCache

_TAG = "[Steam·账户绑定]"
_LANG = "schinese"
# 装扮缓存类型：key 为 steamid64，value 为一次抓取的直链记录
_DECO_CACHE_TYPE = "profile_deco"


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


async def load_custom_url(steamid64: str) -> str:
    """取个人资料页的自定义域名（customURL）；未设置时返回空串。"""
    xml = await get_community_profile_xml(steamid64, base_url=community_base())
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        raise ValueError("Steam 资料解析失败，请稍后重试") from e

    if root.find("error") is not None:
        raise ValueError("该 steamid 不存在或资料不可见")
    return (root.findtext("customURL") or "").strip()


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


class _DecoRecord(TypedDict):
    """一次装扮抓取得到的直链快照；落盘与否由用到的调用方各自决定。"""

    animated_avatar_url: str
    avatar_url: str
    frame_url: str
    mini_background_url: str
    profile_background_url: str
    background_webm_url: str
    background_mp4_url: str
    level: int
    badge_name: str
    badge_icon_url: str
    badge_xp: str
    equipped_ok: bool


def _empty_record() -> _DecoRecord:
    """装扮抓取整体失败时的空记录，字段与正常记录同构，下游无需判空。"""
    return _DecoRecord(
        animated_avatar_url="",
        avatar_url="",
        frame_url="",
        mini_background_url="",
        profile_background_url="",
        background_webm_url="",
        background_mp4_url="",
        level=0,
        badge_name="",
        badge_icon_url="",
        badge_xp="",
        equipped_ok=False,
    )


async def _downloaded_decorations(record: _DecoRecord, *, force: bool = False) -> _Decorations:
    """把装扮记录里的直链落 img_cache，返回文件名；取不到的位为空串。"""
    frame_name, background_name, badge_icon_name = await asyncio.gather(
        _download_name(record["frame_url"], force=force),
        _download_name(record["mini_background_url"], force=force),
        _download_name(record["badge_icon_url"], force=force),
    )
    return _Decorations(
        frame_name=frame_name,
        background_name=background_name,
        level=record["level"],
        badge_name=record["badge_name"],
        badge_icon_name=badge_icon_name,
    )


async def load_profile_assets(steamid64: str, *, force: bool = False) -> SteamProfile:
    """抓取完整资料：昵称头像来自社区 XML，装扮与背景取自装扮记录。

    任一来源失败只缺省对应字段，不影响昵称与头像；force 为真时重取装扮并重下图片。
    """
    base, record = await asyncio.gather(
        _fetch_base_profile(steamid64, force=force),
        _deco_record(steamid64, force=force),
        return_exceptions=True,
    )
    if isinstance(base, BaseException):
        raise base

    if isinstance(record, BaseException):
        logger.warning(f"{_TAG} 装扮获取失败 {steamid64}: {record!r}")
        record = _empty_record()

    decorations = await _downloaded_decorations(record, force=force)
    return replace(
        base,
        frame_name=decorations.frame_name,
        background_name=decorations.background_name,
        level=decorations.level,
        badge_name=decorations.badge_name,
        badge_icon_name=decorations.badge_icon_name,
    )


async def load_mini_background_name(steamid64: str) -> str:
    """取迷你资料背景并落 img_cache；未装扮或取不到时返回空串。"""
    record = await _deco_record(steamid64)
    return await _download_name(record["mini_background_url"])


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


_EquippedKey = Literal["profile_background", "mini_profile_background", "avatar_frame", "animated_avatar"]


def _equipped_item(payload: ProfileItemsEquippedPayload, key: _EquippedKey) -> ProfileItemEntry:
    """取装备项；未装备时返回空条目。"""
    if key in payload:
        return payload[key]
    return ProfileItemEntry()


def _item_large_url(item: ProfileItemEntry) -> str:
    """装备项大图（背景静态首帧）直链；无图返回空串。"""
    return _community_asset_url(item["image_large"] if "image_large" in item else "")


def _item_small_url(item: ProfileItemEntry) -> str:
    """装备项小图（头像 / 头像框）直链；无图返回空串。"""
    return _community_asset_url(item["image_small"] if "image_small" in item else "")


def _mini_background_url(payload: ProfileItemsEquippedPayload) -> str:
    """装配项迷你资料背景直链；未装备返回空串。"""
    return _item_large_url(_equipped_item(payload, "mini_profile_background"))


def _profile_background_url(payload: ProfileItemsEquippedPayload) -> str:
    """装配项个人资料背景直链；未装备返回空串。"""
    return _item_large_url(_equipped_item(payload, "profile_background"))


async def _fetch_equipped_payload(steamid64: str) -> ProfileItemsEquippedPayload | None:
    """取装备项响应；未配置 API Key 时返回 None。"""
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not has_api_key(keys):
        return None
    return await request_with_api_key(
        partial(_request_equipped, steamid64, _LANG),
        keys,
        cooldown_seconds=SteamConfig.get_config("KeyPoolCooldown").data,
    )


async def _cached_record(steamid64: str) -> _DecoRecord | None:
    """读装扮缓存；记录里装配项缺失而现在已配 Key 时视为未命中，以便补取装配项。"""
    cached = await SteamCache.get_value(_DECO_CACHE_TYPE, steamid64)
    if not cached:
        return None
    record = msgspec.json.decode(cached, type=_DecoRecord)
    if not record["equipped_ok"] and has_api_key(SteamConfig.get_config("SteamAPIKey").data):
        return None
    return record


async def _fetch_record(steamid64: str) -> tuple[_DecoRecord, bool]:
    """抓一次装扮直链，返回 (记录, 迷你资料是否成功)。

    两个来源各自失败只丢对应字段；迷你资料失败不落缓存，避免故障期写入空记录。
    """
    mini_raw, equipped_raw = await asyncio.gather(
        get_miniprofile(steamid64, lang=_LANG, base_url=community_base()),
        _fetch_equipped_payload(steamid64),
        return_exceptions=True,
    )
    # 空响应（资料不可见等）同样不落缓存，否则空记录会压住 3 天
    mini_ok = not isinstance(mini_raw, BaseException) and bool(mini_raw)
    if isinstance(mini_raw, BaseException):
        logger.warning(f"{_TAG} 迷你资料获取失败 {steamid64}: {mini_raw!r}")
        mini = MiniprofilePayload()
    else:
        mini = mini_raw

    if isinstance(equipped_raw, BaseException):
        logger.warning(f"{_TAG} 装备项获取失败 {steamid64}: {equipped_raw!r}")
        equipped = ProfileItemsEquippedPayload()
    elif equipped_raw is None:
        equipped = ProfileItemsEquippedPayload()
    else:
        equipped = equipped_raw

    deco = _parse_miniprofile(mini)
    animated = _equipped_item(equipped, "animated_avatar")
    frame = _equipped_item(equipped, "avatar_frame")
    record = _DecoRecord(
        animated_avatar_url=_item_small_url(animated),
        avatar_url=mini["avatar_url"] if "avatar_url" in mini else "",
        # 头像框与迷你背景都是装配项优先、取不到回落迷你资料
        frame_url=_item_small_url(frame) or deco.frame_url,
        mini_background_url=_mini_background_url(equipped) or deco.background_url,
        profile_background_url=_profile_background_url(equipped),
        background_webm_url=deco.background_webm_url,
        background_mp4_url=deco.background_mp4_url,
        level=deco.level,
        badge_name=deco.badge_name,
        badge_icon_url=deco.badge_icon_url,
        badge_xp=deco.badge_xp,
        equipped_ok=not isinstance(equipped_raw, BaseException) and equipped_raw is not None,
    )
    return record, mini_ok


async def _deco_record(steamid64: str, *, force: bool = False) -> _DecoRecord:
    """取装扮记录：缓存优先；缓存不适用或 force 为真时重取并覆盖写。"""
    if not force:
        cached = await _cached_record(steamid64)
        if cached is not None:
            return cached

    record, mini_ok = await _fetch_record(steamid64)
    if mini_ok:
        encoded = msgspec.json.encode(record).decode("utf-8")
        await SteamCache.upsert(_DECO_CACHE_TYPE, steamid64, encoded, int(time.time()))
    return record


async def load_card_background_name(steamid64: str, *, force: bool = False) -> str:
    """取账号个人资料背景文件名供卡片底图使用；开关关闭或取不到时返回空串。"""
    if not use_profile_card_bg():
        return ""
    record = await _deco_record(steamid64, force=force)
    return await _download_name(record["profile_background_url"], force=force)


async def load_frame_name(steamid64: str) -> str:
    """取用户静态头像框文件名（走装扮缓存）；无框或取不到时返回空串。"""
    record = await _deco_record(steamid64)
    return await _download_name(record["frame_url"])


async def load_initiator_card_background_name(ev: Event, *, force: bool = False) -> str:
    """指令发起人主账号的个人资料背景文件名；未绑定主账号时返回空串。"""
    steamid64 = await get_main_steamid64(ev, ev.user_id)
    if steamid64 is None:
        return ""
    return await load_card_background_name(steamid64, force=force)


async def load_status_assets(steamid64: str, *, fallback_avatar_url: str = "") -> StatusAssets:
    """取状态卡素材：装扮记录优先，素材统一落 img_cache。

    fallback_avatar_url 用于装扮全部缺失时兜底摘要头像。
    """
    record = await _deco_record(steamid64)
    avatar_url = record["animated_avatar_url"] or record["avatar_url"] or fallback_avatar_url
    avatar_name, frame_name, background_name, webm_name, mp4_name, badge_icon_name = await asyncio.gather(
        _download_name(avatar_url),
        _download_name(record["frame_url"]),
        _download_name(record["mini_background_url"]),
        _download_name(record["background_webm_url"]),
        _download_name(record["background_mp4_url"]),
        _download_name(record["badge_icon_url"]),
    )
    return StatusAssets(
        avatar_name=avatar_name,
        # 装扮动图头像命中时 avatar_name 即动态素材，判定是否出 GIF 用
        animated_avatar_name=avatar_name if record["animated_avatar_url"] else "",
        frame_name=frame_name,
        background_name=background_name,
        background_webm_name=webm_name,
        background_mp4_name=mp4_name,
        level=record["level"],
        badge_name=record["badge_name"],
        badge_icon_name=badge_icon_name,
        badge_xp=record["badge_xp"],
    )
