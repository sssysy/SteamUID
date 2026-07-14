import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger

from ..utils.database.models_cache import SteamApiCache, SteamArchivementCache

CACHE_DIR: Path = get_res_path("SteamUID") / "cache"


async def purge_db_cache(days: int | None = None) -> tuple[int, int]:
    """清除数据库缓存。

    Args:
        days: 过期天数。传入则只清除指定天数前的缓存；
              不传入（None）则清除全部缓存。

    Returns:
        (deleted_api, deleted_ach)
    """
    if days is not None and days <= 0:
        return (0, 0)

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        cutoff = None

    try:
        if cutoff is not None:
            deleted_api = await SteamApiCache.delete_stale(cutoff)
            deleted_ach = await SteamArchivementCache.delete_stale(cutoff)
        else:
            deleted_api = await SteamApiCache.delete_all()
            deleted_ach = await SteamArchivementCache.delete_all()

        logger.info(
            f"[SteamCache] 数据库缓存清理完成: "
            f"接口缓存删除 {deleted_api} 行, "
            f"成就Schema缓存删除 {deleted_ach} 行"
        )
        return (deleted_api, deleted_ach)
    except Exception as error:
        logger.warning(f"[SteamCache] 数据库缓存清理失败: {error!r}")
        return (0, 0)


async def purge_file_cache(days: int | None = None) -> int:
    """清除文件系统缓存。

    Args:
        days: 过期天数。传入则只清除指定天数前的缓存文件；
              不传入（None）则清除全部缓存文件。

    Returns:
        删除的文件数量。
    """
    if days is not None and days <= 0:
        return 0

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        cutoff = None

    try:
        deleted_files = await asyncio.to_thread(_purge_cache_files, cutoff)
        logger.info(f"[SteamCache] 缓存文件清理完成: 删除 {deleted_files} 个文件")
        return deleted_files
    except Exception as error:
        logger.warning(f"[SteamCache] 缓存文件清理失败: {error!r}")
        return 0


async def purge_all() -> tuple[int, int, int]:
    """清除全部缓存（数据库 + 文件系统）。

    Returns:
        (deleted_api, deleted_ach, deleted_files)
    """
    deleted_api, deleted_ach = await purge_db_cache()
    deleted_files = await purge_file_cache()
    return (deleted_api, deleted_ach, deleted_files)


def _purge_cache_files(cutoff: datetime | None) -> int:
    """删除 CACHE_DIR 中过期的缓存文件。

    Args:
        cutoff: 截止时间。None 表示删除全部文件。

    Returns:
        删除的文件数量。
    """
    if not CACHE_DIR.exists():
        return 0

    count = 0
    for f in CACHE_DIR.iterdir():
        if not f.is_file():
            continue
        if cutoff is None:
            f.unlink(missing_ok=True)
            count += 1
        else:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink(missing_ok=True)
                count += 1
    return count
