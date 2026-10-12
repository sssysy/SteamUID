"""商店详情缓存与简介清洗：详情落 SteamCache，供封面与推荐共用。

只取回并缓存 AppDetailsEntry；直链挑选与文案拼装由调用方自行处理。
"""

import re
import html
import time

import httpx
import msgspec

from gsuid_core.logger import logger

from .config import store_base
from ..api.models import AppDetailsEntry
from ..api.public import get_game_details
from ..database.model_cache import SteamCache

_TAG = "[Steam·游戏详情]"
_LANG = "schinese"

# 缓存类型共享给封面解析，键为 appid；换名会让旧缓存失效
STORE_DETAIL_CACHE_TYPE = "store_detail"

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
