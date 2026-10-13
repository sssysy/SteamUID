"""商店详情缓存、steamcmd PICS 补搜与简介清洗。

只取回并缓存 AppDetailsEntry；直链挑选与文案拼装由调用方自行处理。
"""

import re
import html
import time
import asyncio
from typing import TypedDict
from collections.abc import Mapping, Sequence

import httpx
import msgspec

from gsuid_core.logger import logger

from .config import store_base
from ..api.pics import get_app_info
from ..api.cover import build_app_icon_url, build_store_asset_url
from ..api.models import AppDetailsEntry, PicsInfoResponse
from ..api.public import get_game_details
from ..database.model_cache import SteamCache

_TAG = "[Steam·游戏详情]"
_LANG = "schinese"

# 缓存类型共享给封面解析，键为 appid；换名会让旧缓存失效
STORE_DETAIL_CACHE_TYPE = "store_detail"
# PICS 补搜缓存，键为 appid + 语言，换地区后不会串名
_PICS_CACHE_TYPE = "app_meta"
# 补搜逐 appid 请求，分批并发避免一次打太多
_NAME_BATCH = 10

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


async def load_store_detail(appid: str, cc: str | None) -> AppDetailsEntry | None:
    """商店详情：命中缓存直接复用，未命中请求并回写；请求失败返回 None。"""
    cached = await SteamCache.get_value(STORE_DETAIL_CACHE_TYPE, appid)
    if cached:
        return msgspec.json.decode(cached, type=AppDetailsEntry)

    try:
        entry = await get_game_details(appid, lang=_LANG, cc=cc, base_url=store_base())
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_TAG} 商店详情查询失败 appid={appid} cc={cc}: {type(error).__name__}")
        return None

    # 只有 success + data 的结构才落缓存，避免把失败响应当成命中
    if "success" in entry and entry["success"] and "data" in entry:
        encoded = msgspec.json.encode(entry).decode("utf-8")
        await SteamCache.upsert(STORE_DETAIL_CACHE_TYPE, appid, encoded, int(time.time()))
    return entry


def clean_description(text: str) -> str:
    """去掉简介里的 HTML 标签与实体，并把连续空白压成单空格。"""
    if not text:
        return ""
    unescaped = html.unescape(text)
    return _WS_RE.sub(" ", _TAG_RE.sub("", unescaped)).strip()


def store_detail_name(detail: AppDetailsEntry | None) -> str:
    """商店详情里的游戏名；未成功或缺字段返回空串。"""
    if detail is None or "success" not in detail or not detail["success"] or "data" not in detail:
        return ""
    data = detail["data"]
    return data["name"] if "name" in data else ""


class PicsMeta(TypedDict, total=False):
    """PICS 元数据：本地化游戏名、方形图标与官方横板图直链。"""

    name: str
    icon_url: str
    cover_url: str


def _pics_meta(payload: PicsInfoResponse, appid: str, lang: str) -> PicsMeta:
    """从 PICS 提取本地化名、方形图标与官方封面直链；缺失项各自回落。"""
    data = payload["data"] if "data" in payload else {}
    entry = data[appid] if appid in data else None
    common = entry["common"] if entry is not None and "common" in entry else None
    if common is None:
        return PicsMeta()

    meta = PicsMeta()
    localized = common["name_localized"] if "name_localized" in common else {}
    name = localized[lang] if lang in localized else (common["name"] if "name" in common else "")
    if name:
        meta["name"] = name

    icon = common["icon"] if "icon" in common else ""
    if icon:
        meta["icon_url"] = build_app_icon_url(appid, icon)

    images = common["header_image"] if "header_image" in common else {}
    path = images[lang] if lang in images else (images["english"] if "english" in images else "")
    if path:
        meta["cover_url"] = build_store_asset_url(appid, path)
    return meta


async def pics_game_meta(appid: str, *, lang: str) -> PicsMeta:
    """steamcmd PICS 元数据：缓存优先，未收录或请求失败返回空记录。"""
    aid = appid.strip()
    if not aid.isdigit():
        return PicsMeta()

    cache_key = f"{aid}|{lang}"
    cached = await SteamCache.get_value(_PICS_CACHE_TYPE, cache_key)
    if cached:
        return msgspec.json.decode(cached, type=PicsMeta)

    try:
        payload = await get_app_info(aid)
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_TAG} steamcmd 查询失败 appid={aid}: {type(error).__name__}")
        return PicsMeta()

    meta = _pics_meta(payload, aid, lang)
    if not meta:
        return meta
    encoded = msgspec.json.encode(meta).decode("utf-8")
    await SteamCache.upsert(_PICS_CACHE_TYPE, cache_key, encoded, int(time.time()))
    return meta


async def pics_game_name(appid: str, *, lang: str) -> str:
    """steamcmd PICS 里的游戏名；未收录或请求失败返回空串。"""
    meta = await pics_game_meta(appid, lang=lang)
    return meta["name"] if "name" in meta else ""


async def resolve_game_name(appid: str, *, cc: str, lang: str) -> str:
    """游戏名：商店详情优先，取不到时补搜 steamcmd PICS 名，都取不到返回空串。"""
    name = store_detail_name(await load_store_detail(appid, cc))
    return name if name else await pics_game_name(appid, lang=lang)


async def resolve_game_names(
    appids: Sequence[str],
    *,
    cc: str,
    lang: str,
    details: Mapping[str, AppDetailsEntry | None] | None = None,
) -> dict[str, str]:
    """批量解析游戏名，返回 appid 到名字的映射（只含成功项）。

    调用方已取到商店详情时经 details 传入，避免重复请求。
    """
    ordered = list(dict.fromkeys(appid.strip() for appid in appids if appid.strip()))
    if not ordered:
        return {}
    sem = asyncio.Semaphore(_NAME_BATCH)

    async def one(appid: str) -> str:
        async with sem:
            if details is not None and appid in details:
                name = store_detail_name(details[appid])
            else:
                name = store_detail_name(await load_store_detail(appid, cc))
            return name if name else await pics_game_name(appid, lang=lang)

    resolved = await asyncio.gather(*(one(appid) for appid in ordered))
    return {appid: name for appid, name in zip(ordered, resolved) if name}
