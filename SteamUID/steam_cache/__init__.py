"""Steam 数据缓存的定时清理任务注册。"""

import time

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

from ..steam_config import get_cache_clean_days
from ..utils.database.model_cache import SteamCache
from ..utils.downloader import clean_cache_files

_TAG = "[Steam·缓存清理]"

_CLEAN_DAYS = get_cache_clean_days()

# 0 表示不清理，且 interval 的 days 不能为 0，直接不注册任务
if _CLEAN_DAYS > 0:

    @scheduler.scheduled_job("interval", days=_CLEAN_DAYS)
    async def clean_steam_cache_job() -> None:
        cutoff = int(time.time()) - _CLEAN_DAYS * 86400
        deleted = await SteamCache.delete_expired(cutoff)
        removed = await clean_cache_files(cutoff)
        logger.info(
            f"{_TAG} 清理 {_CLEAN_DAYS} 天前的缓存，删除 {deleted} 行 / {removed} 个文件"
        )
