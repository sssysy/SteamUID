"""游戏封面解析：用户区官方图 -> 全球区官方图 -> SteamGridDB 社区封面。

命中后把图片落 img_cache 并返回文件名，直链拼接由上层渲染层负责。
"""

import time
import asyncio
from collections.abc import Sequence

import httpx
import msgspec

from gsuid_core.logger import logger

from ..api.cover import fetch_griddb_grids, get_official_cover_url, fetch_griddb_grids_batch
from ..api.models import GridDbGrid, GridDbBatchEntry, GridDbGridsResponse
from ..downloader import download
from .game_detail import load_store_detail
from ..database.model_cache import SteamCache

_TAG = "[Steam·游戏封面]"
_CACHE_TYPE = "game_cover"
_GRIDDB_CACHE_TYPE = "griddb_cover"

# 商店详情逐游戏请求，分批并发避免一次打太多
_DETAIL_CHUNK = 10
# GridDB 批量查询单请求携带的游戏数上限
_GRIDDB_BATCH_SIZE = 50


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
    entry = await load_store_detail(appid, cc)
    if entry is None:
        return ""
    if "success" not in entry or not entry["success"] or "data" not in entry:
        return ""
    data = entry["data"]
    return data["header_image"] if "header_image" in data else ""


def _first_grid_url(payload: GridDbGridsResponse) -> str:
    """取候选里的首个直链，保持接口默认的票数排序。"""
    grids = payload["data"] if "data" in payload else []
    for grid in grids:
        url = grid["url"] if "url" in grid else ""
        if url:
            return url
    return ""


async def _griddb_cover(appid: str, api_key: str) -> str:
    """SteamGridDB 最高票横板图直链；接口异常或无结果返回空串。"""
    cached = await SteamCache.get_value(_GRIDDB_CACHE_TYPE, appid)
    if cached:
        return _first_grid_url(msgspec.json.decode(cached, type=GridDbGridsResponse))

    try:
        payload = await fetch_griddb_grids(appid, api_key=api_key)
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_TAG} GridDB 查询失败 appid={appid}: {type(error).__name__}")
        return ""
    url = _first_grid_url(payload)
    if not url:
        return ""
    encoded = msgspec.json.encode(payload).decode("utf-8")
    await SteamCache.upsert(_GRIDDB_CACHE_TYPE, appid, encoded, int(time.time()))
    return url


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


async def _download_names(urls: Sequence[str]) -> list[str]:
    """并发落盘一批封面，返回与入参对齐的文件名；失败位为空串。"""
    paths = await download(list(urls), kind="image")
    return [path.name if path is not None else "" for path in paths]


def _first_grid_url_of(grids: Sequence[GridDbGrid]) -> str:
    """取候选里的首个直链，保持接口默认的票数排序。"""
    for grid in grids:
        if "url" in grid and grid["url"]:
            return grid["url"]
    return ""


async def _griddb_cover_urls(appids: Sequence[str], api_key: str) -> list[str]:
    """批量取 GridDB 最高票封面直链；未收录或响应错位的位置回落空串。"""
    try:
        entries: list[GridDbBatchEntry] = await fetch_griddb_grids_batch(appids, api_key=api_key)
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_TAG} GridDB 批量查询失败: {type(error).__name__}")
        return ["" for _ in appids]

    # 条目与请求顺序对齐，数量不符时无法安全映射到 appid
    if len(entries) != len(appids):
        logger.warning(f"{_TAG} GridDB 批量返回数量与请求不一致 请求={len(appids)} 返回={len(entries)}")
        return ["" for _ in appids]

    urls: list[str] = []
    for entry in entries:
        if "status" not in entry or entry["status"] != 200:
            urls.append("")
            continue
        grids: list[GridDbGrid] = entry["data"] if "data" in entry else []
        urls.append(_first_grid_url_of(grids))
    return urls


async def resolve_cover_names(
    appids: Sequence[str],
    *,
    country: str,
    griddb_key: str,
) -> dict[str, str]:
    """批量解析封面并落 img_cache，返回 appid 到文件名的映射（只含成功项）。

    回退顺序：官方 CDN 直链 -> 商店详情 header_image -> SteamGridDB 社区封面。
    """
    ordered = list(dict.fromkeys(appid.strip() for appid in appids if appid.strip()))
    if not ordered:
        return {}

    official = {appid: get_official_cover_url(appid, "header") for appid in ordered}
    names: dict[str, str] = {}
    for appid, name in zip(ordered, await _download_names([official[a] for a in ordered])):
        if name:
            names[appid] = name

    remaining = [appid for appid in ordered if appid not in names]
    cc = country.strip() or None
    for start in range(0, len(remaining), _DETAIL_CHUNK):
        chunk = remaining[start : start + _DETAIL_CHUNK]
        details = await asyncio.gather(*(_store_header(appid, cc) for appid in chunk))
        # 详情接口返回的常与官方直链同址，同址不再重复下载
        candidates = [url if url != official[appid] else "" for appid, url in zip(chunk, details)]
        for appid, name in zip(chunk, await _download_names(candidates)):
            if name:
                names[appid] = name

    remaining = [appid for appid in ordered if appid not in names]
    if griddb_key and remaining:
        for start in range(0, len(remaining), _GRIDDB_BATCH_SIZE):
            chunk = remaining[start : start + _GRIDDB_BATCH_SIZE]
            urls = await _griddb_cover_urls(chunk, griddb_key)
            for appid, name in zip(chunk, await _download_names(urls)):
                if name:
                    names[appid] = name

    return names
