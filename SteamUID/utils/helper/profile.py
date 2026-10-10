"""Steam 玩家资料抓取：社区资料 XML + 迷你资料，图片经 downloader 落 img_cache。

只返回 img_cache 文件名，直链拼接由上层渲染层负责，避免 helper 反向依赖 render。
"""

import asyncio
from xml.etree import ElementTree
from dataclasses import replace, dataclass

from gsuid_core.logger import logger

from .steamid import steamid64_to_friend_code
from ..api.public import get_miniprofile, get_community_profile_xml
from ..downloader import download

_TAG = "[Steam·账户绑定]"
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


async def _download_name(url: str) -> str:
    """下载图片到 img_cache，返回文件名；空 URL 或下载失败返回空串。"""
    if not url.strip():
        return ""
    path = await download(url, kind="image")
    return path.name if path is not None else ""


def _parse_profile_xml(xml: str) -> tuple[str, str]:
    """解析社区资料 XML，返回 (昵称, 头像原链)；资料不可见时抛 ValueError。"""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        raise ValueError("Steam 资料解析失败，请稍后重试") from e

    if root.find("error") is not None:
        raise ValueError("该 steamid 不存在或资料不可见")

    name = (root.findtext("steamID") or "").strip()
    avatar = (root.findtext("avatarFull") or root.findtext("avatarMedium") or "").strip()
    if not name and not avatar:
        raise ValueError("该 steamid 不存在或资料不可见")
    return name, avatar


async def _fetch_base_profile(steamid64: str) -> SteamProfile:
    xml = await get_community_profile_xml(steamid64)
    name, avatar = _parse_profile_xml(xml)
    return SteamProfile(
        steamid64=steamid64,
        name=name,
        friend_code=steamid64_to_friend_code(steamid64),
        avatar_name=await _download_name(avatar),
        frame_name="",
        background_name="",
    )


async def _fetch_decorations(steamid64: str) -> tuple[str, str]:
    """取头像框与迷你资料背景，返回 img_cache 文件名；接口异常向上抛出。"""
    payload = await get_miniprofile(steamid64, lang=_LANG)

    frame = payload["avatar_frame"] if "avatar_frame" in payload else ""
    background = ""
    if "profile_background" in payload:
        background_map = payload["profile_background"]
        if "image" in background_map:
            background = background_map["image"]

    return await _download_name(frame), await _download_name(background)


async def load_profile_assets(steamid64: str) -> SteamProfile:
    """抓取完整资料；迷你资料接口失败时仅缺省头像框与背景，不影响昵称与头像。"""
    base, decorations = await asyncio.gather(
        _fetch_base_profile(steamid64),
        _fetch_decorations(steamid64),
        return_exceptions=True,
    )
    if isinstance(base, BaseException):
        raise base

    if isinstance(decorations, BaseException):
        logger.warning(f"{_TAG} 迷你资料获取失败 {steamid64}: {decorations!r}")
        return base

    frame_name, background_name = decorations
    return replace(base, frame_name=frame_name, background_name=background_name)
