from datetime import datetime, timedelta, timezone

from gsuid_core.logger import logger

from ..SteamConfig import SteamConfig
from ..utils.database.models_cache import SteamApiCache, SteamArchivementCache


async def purge_stale_caches() -> None:
    """清理过期缓存行：删除 updated_at 早于 CacheTime 天前的缓存。"""
    cache_days = SteamConfig.get_config("CacheTime").data
    if not cache_days or cache_days <= 0:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=cache_days)

    try:
        deleted_api = await SteamApiCache.delete_stale(cutoff)
        deleted_ach = await SteamArchivementCache.delete_stale(cutoff)
        if deleted_api or deleted_ach:
            logger.info(
                f"[SteamPoll] 缓存清理完成: "
                f"接口缓存删除 {deleted_api} 行, "
                f"成就Schema缓存删除 {deleted_ach} 行"
            )
    except Exception as error:
        logger.warning(f"[SteamPoll] 缓存清理失败: {error!r}")
