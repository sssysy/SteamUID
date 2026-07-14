from ..SteamConfig import SteamConfig
from ..SteamCache.cache_service import purge_db_cache, purge_file_cache


async def purge_stale_caches() -> None:
    """清理过期数据库缓存：删除超过 CacheTime 天的接口缓存和成就缓存。"""
    cache_days = SteamConfig.get_config("CacheTime").data
    if not cache_days or cache_days <= 0:
        return

    await purge_db_cache(days=cache_days)


async def purge_stale_files() -> None:
    """清理过期缓存文件：删除超过 FileCacheTime 天的缓存文件。"""
    file_cache_days = SteamConfig.get_config("FileCacheTime").data
    if not file_cache_days or file_cache_days <= 0:
        return

    await purge_file_cache(days=file_cache_days)
