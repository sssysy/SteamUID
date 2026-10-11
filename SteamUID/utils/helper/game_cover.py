"""游戏封面解析：用户区官方图 -> 全球区官方图 -> SteamGridDB 社区封面。

命中后把图片落 img_cache 并返回文件名，直链拼接由上层渲染层负责。
"""

import time

import httpx
from gsuid_core.logger import logger

from ..api.cover import fetch_griddb_grids
from ..api.public import get_game_details
from ..database.model_cache import SteamCache
from ..downloader import download

_TAG = "[Steam·游戏封面]"
_CACHE_TYPE = "game_cover"
_LANG = "schinese"


async def _download_name(url: str) -> str:
    """落地封面图，返回 img_cache 文件名；空 URL 或下载失败返回空串。"""
    if not url.strip():
        return ""
    try:
        path = await download(url, kind="image")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 封面下载失败: {type(error).__name__}")
        return ""
    return path.name if path is not None else ""


async def _store_header(appid: str, cc: str | None) -> str:
    """商店详情的 header_image 直链；接口异常、未成功或缺字段都返回空串。"""
    try:
        entry = await get_game_details(appid, lang=_LANG, cc=cc)
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_TAG} 商店详情查询失败 appid={appid} cc={cc}: {type(error).__name__}")
        return ""
    if "success" not in entry or not entry["success"]:
        return ""
    if "data" not in entry:
        return ""
    data = entry["data"]
    return data["header_image"] if "header_image" in data else ""


async def _griddb_cover(appid: str, api_key: str) -> str:
    """SteamGridDB 最高票横板图直链；接口异常或无结果返回空串。"""
    try:
        payload = await fetch_griddb_grids(appid, api_key=api_key)
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_TAG} GridDB 查询失败 appid={appid}: {type(error).__name__}")
        return ""
    grids = payload["data"] if "data" in payload else []
    for grid in grids:
        url = grid["url"] if "url" in grid else ""
        if url:
            return url
    return ""


async def resolve_cover_name(appid: str, *, country: str, griddb_key: str) -> str:
    """三级回退解析封面并落 img_cache，返回文件名；全部失败返回空串。

    命中过的直链写入 SteamCache，后续轮次直接复用；缓存直链失效则重新回退。
    """
    if not appid.strip():
        return ""

    cached = await SteamCache.get_value(_CACHE_TYPE, appid)
    if cached:
        name = await _download_name(cached)
        if name:
            return name

    if country:
        candidates = [await _store_header(appid, country), await _store_header(appid, None)]
    else:
        candidates = [await _store_header(appid, None)]
    if griddb_key:
        candidates.append(await _griddb_cover(appid, griddb_key))

    for url in candidates:
        if not url:
            continue
        name = await _download_name(url)
        if not name:
            continue
        await SteamCache.upsert(_CACHE_TYPE, appid, url, int(time.time()))
        return name
    return ""
