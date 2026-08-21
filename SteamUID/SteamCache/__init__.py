import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from gsuid_core.bot import Bot
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.database.models_cache import SteamApiCache, SteamArchivementCache

CACHE_DIR: Path = get_res_path("SteamUID") / "cache"


class DbCachePurgeResult(NamedTuple):
    api_count: int
    ach_count: int
    success: bool


class FileCachePurgeResult(NamedTuple):
    file_count: int
    success: bool


class AllCachePurgeResult(NamedTuple):
    api_count: int
    ach_count: int
    file_count: int
    success: bool


async def purge_db_cache(days: int | None = None) -> DbCachePurgeResult:
    """清除数据库缓存。

    Args:
        days: 过期天数。传入则只清除指定天数前的缓存；
              不传入（None）则清除全部缓存。

    Returns:
        DbCachePurgeResult(api_count, ach_count, success)
    """
    if days is not None and days <= 0:
        return DbCachePurgeResult(0, 0, True)

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        cutoff = None

    deleted_api = 0
    deleted_ach = 0
    errors: list[str] = []

    try:
        if cutoff is not None:
            deleted_api = await SteamApiCache.delete_stale(cutoff)
        else:
            deleted_api = await SteamApiCache.delete_all()
    except Exception as error:
        logger.warning(f"[SteamCache] 数据库接口缓存清理失败: {error!r}")
        errors.append(f"接口缓存: {error!r}")

    try:
        if cutoff is not None:
            deleted_ach = await SteamArchivementCache.delete_stale(cutoff)
        else:
            deleted_ach = await SteamArchivementCache.delete_all()
    except Exception as error:
        logger.warning(f"[SteamCache] 数据库成就Schema缓存清理失败: {error!r}")
        errors.append(f"成就Schema缓存: {error!r}")

    if errors:
        logger.warning(
            f"[SteamCache] 数据库缓存清理未完全成功: {'; '.join(errors)}"
        )
        return DbCachePurgeResult(deleted_api, deleted_ach, False)

    logger.info(
        f"[SteamCache] 数据库缓存清理完成: "
        f"接口缓存删除 {deleted_api} 行, "
        f"成就Schema缓存删除 {deleted_ach} 行"
    )
    return DbCachePurgeResult(deleted_api, deleted_ach, True)


async def purge_file_cache(days: int | None = None) -> FileCachePurgeResult:
    """清除文件系统缓存。

    Args:
        days: 过期天数。传入则只清除指定天数前的缓存文件；
              不传入（None）则清除全部缓存文件。

    Returns:
        FileCachePurgeResult(file_count, success)
    """
    if days is not None and days <= 0:
        return FileCachePurgeResult(0, True)

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        cutoff = None

    try:
        deleted_files, success = await asyncio.to_thread(_purge_cache_files, cutoff)
        if success:
            logger.info(f"[SteamCache] 缓存文件清理完成: 删除 {deleted_files} 个文件")
        else:
            logger.warning(f"[SteamCache] 缓存文件清理未完全成功: 已删除 {deleted_files} 个文件")
        return FileCachePurgeResult(deleted_files, success)
    except Exception as error:
        logger.warning(f"[SteamCache] 缓存文件清理失败: {error!r}")
        return FileCachePurgeResult(0, False)


async def purge_all() -> AllCachePurgeResult:
    """清除全部缓存（数据库 + 文件系统）。

    Returns:
        AllCachePurgeResult(api_count, ach_count, file_count, success)
    """
    db_res = await purge_db_cache()
    file_res = await purge_file_cache()
    success = db_res.success and file_res.success
    return AllCachePurgeResult(
        api_count=db_res.api_count,
        ach_count=db_res.ach_count,
        file_count=file_res.file_count,
        success=success,
    )


def _purge_cache_files(cutoff: datetime | None) -> tuple[int, bool]:
    """删除 CACHE_DIR 中过期的缓存文件。

    Args:
        cutoff: 截止时间。None 表示删除全部文件。

    Returns:
        (deleted_count, success)
    """
    if not CACHE_DIR.exists():
        return (0, True)

    try:
        entries = list(CACHE_DIR.iterdir())
    except Exception as error:
        logger.warning(f"[SteamCache] 读取缓存目录失败: {error!r}")
        return (0, False)

    count = 0
    had_error = False
    for f in entries:
        try:
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
        except Exception as error:
            had_error = True
            logger.warning(f"[SteamCache] 删除缓存文件 {f.name} 失败: {error!r}")

    return (count, not had_error)


sv_steam_cache = SV('steam清除缓存')


@sv_steam_cache.on_command(('清除全部缓存', '删除全部缓存'))
async def clear_all_cache(bot: Bot, ev: Event):
    res = await purge_all()
    status_msg = "已清除全部缓存！" if res.success else "清除全部缓存失败！"
    await bot.send(
        f'[SteamUID] {status_msg}\n'
        f'接口缓存: {res.api_count} 条\n'
        f'成就缓存: {res.ach_count} 条\n'
        f'缓存文件: {res.file_count} 个'
    )


@sv_steam_cache.on_command(('清除本地缓存', '删除本地缓存'))
async def clear_local_cache(bot: Bot, ev: Event):
    res = await purge_file_cache()
    status_msg = "已清除本地缓存！" if res.success else "清除本地缓存失败！"
    await bot.send(
        f'[SteamUID] {status_msg}\n'
        f'缓存文件: {res.file_count} 个'
    )


@sv_steam_cache.on_command(('清除数据库缓存', '删除数据库缓存'))
async def clear_db_cache(bot: Bot, ev: Event):
    res = await purge_db_cache()
    status_msg = "已清除数据库缓存！" if res.success else "清除数据库缓存失败！"
    await bot.send(
        f'[SteamUID] {status_msg}\n'
        f'接口缓存: {res.api_count} 条\n'
        f'成就缓存: {res.ach_count} 条'
    )