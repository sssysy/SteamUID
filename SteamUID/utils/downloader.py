import asyncio
import hashlib
from typing import Literal, overload
from pathlib import Path
from collections.abc import Sequence

import httpx

from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.download_resource.download_file import download as download_file

DATA_DIR: Path = get_res_path("SteamUID")
# 图片统一落 img_cache（已挂载直链）；其它文件落 cache
CACHE_DIR: Path = DATA_DIR / "cache"
IMG_CACHE_DIR: Path = DATA_DIR / "img_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

ResourceKind = Literal["image", "file"]

_TAG = "[Steam·资源下载]"

_VALID_EXTENSIONS: set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".svg",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
}


def get_cache_path(
    url: str,
    save_dir: Path | str | None = None,
    *,
    kind: ResourceKind = "file",
) -> Path:
    """按 md5(url) + 原后缀推导缓存路径；后缀不在白名单时回落 .jpg。"""
    if save_dir is not None:
        target_dir = Path(save_dir)
    else:
        target_dir = IMG_CACHE_DIR if kind == "image" else CACHE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(url.split("?")[0].split("#")[0]).suffix.lower()
    if ext not in _VALID_EXTENSIONS:
        ext = ".jpg"

    return target_dir / f"{hashlib.md5(url.encode('utf-8')).hexdigest()}{ext}"


def _cache_hit(target_path: Path) -> bool:
    """存在且非空才算命中，避免上次失败留下的空文件被当缓存。"""
    return target_path.is_file() and target_path.stat().st_size > 0


def _new_client(timeout: float) -> httpx.AsyncClient:
    """框架 download 默认不跟随重定向，而 Steam 图床常见 302，需显式打开。"""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


async def _download_single(
    client: httpx.AsyncClient,
    url: str,
    target_path: Path,
    force: bool = False,
) -> Path | None:
    """落盘单个 URL，实际下载复用框架 download；失败返回 None。"""
    if not url.strip():
        return None

    if not force and _cache_hit(target_path):
        return target_path

    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 框架 download 无类型标注，返回值在此立即收窄为 int | None
    retcode: int | None = await download_file(url, target_path.parent, target_path.name, sess=client, tag=_TAG)
    if retcode != 200 or not _cache_hit(target_path):
        logger.warning(f"{_TAG} 下载失败: {url}")
        return None

    return target_path


@overload
async def download(
    target: str,
    save_dir: Path | str | None = None,
    *,
    kind: ResourceKind = "file",
    save_path: Path | str | None = None,
    max_concurrency: int = 5,
    timeout: float = 30.0,
    force: bool = False,
) -> Path | None: ...


@overload
async def download(
    target: Sequence[str],
    save_dir: Path | str | None = None,
    *,
    kind: ResourceKind = "file",
    save_path: None = None,
    max_concurrency: int = 5,
    timeout: float = 30.0,
    force: bool = False,
) -> list[Path | None]: ...


async def download(
    target: str | Sequence[str],
    save_dir: Path | str | None = None,
    *,
    kind: ResourceKind = "file",
    save_path: Path | str | None = None,
    max_concurrency: int = 5,
    timeout: float = 30.0,
    force: bool = False,
) -> Path | None | list[Path | None]:
    """统一资源下载入口：单 URL 返回落盘路径或 None，序列按原序返回对齐结果。

    kind 决定未显式指定落盘目录时的默认目录：image 落 img_cache，其余落 cache。
    """
    if isinstance(target, str):
        url = target.strip()
        if not url:
            return None

        dest_path = Path(save_path) if save_path is not None else get_cache_path(url, save_dir=save_dir, kind=kind)
        if not force and _cache_hit(dest_path):
            return dest_path

        async with _new_client(timeout) as client:
            return await _download_single(client, url, dest_path, force=force)

    urls = list(target)
    if not urls:
        return []

    results: list[Path | None] = [None] * len(urls)
    sem = asyncio.Semaphore(max_concurrency)

    async def _worker(client: httpx.AsyncClient, index: int, raw_url: str) -> None:
        url = raw_url.strip()
        if not url:
            return
        # 缓存判定放进信号量内：并发下同 URL 只真正下载一次
        async with sem:
            dest_path = get_cache_path(url, save_dir=save_dir, kind=kind)
            results[index] = await _download_single(client, url, dest_path, force=force)

    async with _new_client(timeout) as client:
        await asyncio.gather(*(_worker(client, i, u) for i, u in enumerate(urls)))

    return results
