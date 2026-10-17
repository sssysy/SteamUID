"""游戏封面解析：商店封面 -> steamcmd PICS 官方图 -> SteamGridDB 社区封面。

命中后把图片落 img_cache，并返回文件名与可复用的 PICS 译名。
"""

import time
import asyncio
from dataclasses import dataclass
from collections.abc import Sequence

import httpx
import msgspec

from gsuid_core.logger import logger

from ..api.cover import fetch_griddb_grids, get_official_cover_url, fetch_griddb_grids_batch
from ..api.models import GridDbGrid, GridDbBatchEntry, GridDbGridsResponse
from ..downloader import download
from .game_detail import pics_game_meta, load_store_detail, cached_pics_game_meta
from ..database.model_cache import SteamCache

_TAG = "[Steam·游戏封面]"
_CACHE_TYPE = "game_cover"
_GRIDDB_CACHE_TYPE = "griddb_cover"

# 商店详情逐游戏请求，分批并发避免一次打太多
_DETAIL_CHUNK = 10
# GridDB 批量查询单请求携带的游戏数上限
_GRIDDB_BATCH_SIZE = 50
# PICS 只有单 appid 接口，回退时按并发上限逐个补
_PICS_BATCH = 10


@dataclass(frozen=True)
class CoverResolution:
    """封面文件名与 PICS 本地化游戏名；未回退 steamcmd 时名字为空串。"""

    image_name: str
    game_name: str = ""


async def download_image_name(url: str) -> str:
    """落地单张图片并返回 img_cache 文件名；空地址或下载失败返回空串。"""
    if not url.strip():
        return ""
    try:
        path = await download(url, kind="image")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 图片下载失败: {type(error).__name__}")
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


async def _pics_cover(appid: str, lang: str) -> str:
    """steamcmd PICS 的官方横板直链；未收录或请求失败返回空串。"""
    meta = await pics_game_meta(appid, lang=lang)
    return meta["cover_url"] if "cover_url" in meta else ""


async def _pics_cover_urls(appids: Sequence[str], lang: str) -> list[str]:
    """并发取 PICS 横板直链，返回与入参对齐的列表；未收录的位置回落空串。"""
    if not appids:
        return []
    sem = asyncio.Semaphore(_PICS_BATCH)

    async def one(appid: str) -> str:
        async with sem:
            return await _pics_cover(appid, lang)

    return list(await asyncio.gather(*(one(appid) for appid in appids)))


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


async def resolve_cover(appid: str, *, country: str, lang: str, griddb_key: str) -> CoverResolution:
    """惰性回退解析封面与 PICS 译名；商店封面成功时不请求 steamcmd。"""
    aid = appid.strip()
    if not aid:
        return CoverResolution(image_name="")

    cached = await SteamCache.get_value(_CACHE_TYPE, aid)
    if cached:
        image_name = await download_image_name(cached)
        if image_name:
            cached_meta = await cached_pics_game_meta(aid, lang=lang)
            game_name = ""
            if (
                cached_meta is not None
                and "cover_url" in cached_meta
                and cached_meta["cover_url"] == cached
                and "name" in cached_meta
            ):
                game_name = cached_meta["name"]
            return CoverResolution(image_name, game_name)

    store_url = await _store_header(aid, country.strip() or None)
    store_name = await download_image_name(store_url)
    if store_name:
        await SteamCache.upsert(_CACHE_TYPE, aid, store_url, int(time.time()))
        return CoverResolution(store_name)

    pics_meta = await pics_game_meta(aid, lang=lang)
    pics_name = pics_meta["name"] if "name" in pics_meta else ""
    if "cover_url" in pics_meta:
        pics_cover = pics_meta["cover_url"]
        pics_image_name = await download_image_name(pics_cover)
        if pics_image_name:
            await SteamCache.upsert(_CACHE_TYPE, aid, pics_cover, int(time.time()))
            return CoverResolution(pics_image_name, pics_name)

    if griddb_key:
        grid_url = await _griddb_cover(aid, griddb_key)
        grid_image_name = await download_image_name(grid_url)
        if grid_image_name:
            await SteamCache.upsert(_CACHE_TYPE, aid, grid_url, int(time.time()))
            return CoverResolution(grid_image_name, pics_name)

    return CoverResolution(image_name="", game_name=pics_name)


async def resolve_cover_name(appid: str, *, country: str, lang: str, griddb_key: str) -> str:
    """只取封面文件名；译名由 resolve_cover 的调用方按需复用。"""
    resolved = await resolve_cover(appid, country=country, lang=lang, griddb_key=griddb_key)
    return resolved.image_name


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
    lang: str,
    griddb_key: str,
) -> dict[str, str]:
    """批量解析封面并落 img_cache，返回 appid 到文件名的映射（只含成功项）。

    回退顺序：官方 CDN 直链 -> 商店详情 header_image -> PICS 官方图 -> SteamGridDB。
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
    if remaining:
        pics_urls = await _pics_cover_urls(remaining, lang)
        for appid, name in zip(remaining, await _download_names(pics_urls)):
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
