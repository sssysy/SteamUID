from gsuid_core.aps import scheduler

from ..SteamCache import purge_db_cache, purge_file_cache
from ..SteamConfig import SteamConfig
from . import poll_service

# steam 游戏状态轮询
@scheduler.scheduled_job(
    'interval',
    seconds=SteamConfig.get_config("PollInterval").data,
)
async def get_user_Summaries_job():
    await poll_service.poll_and_push_game_status()

# steam 成就状态轮询
@scheduler.scheduled_job(
    'interval',
    seconds=SteamConfig.get_config("ArchivementsPollInterval").data,
)
async def check_archivement():
    await poll_service.poll_and_push_achievements()

# steam 游戏降价状态轮询
@scheduler.scheduled_job(
    'interval',
    hours=SteamConfig.get_config("GameSaleInterval").data,
)
async def check_game_sale():
    await poll_service.poll_and_push_game_sale()

# steam 数据库缓存清理
@scheduler.scheduled_job(
    'interval',
    days=SteamConfig.get_config("CacheTime").data,
)
async def purge_cache():
    cache_days = SteamConfig.get_config("CacheTime").data
    if cache_days and cache_days > 0:
        await purge_db_cache(days=cache_days)

# steam 缓存文件清理（FileCacheTime 为 0 时不启用）
_file_cache_days = SteamConfig.get_config("FileCacheTime").data
if _file_cache_days and _file_cache_days > 0:
    @scheduler.scheduled_job(
        'interval',
        days=_file_cache_days,
    )
    async def purge_file_cache_job():
        await purge_file_cache(days=_file_cache_days)


# steam 每日自动探索队列任务
def _parse_discovery_queue_time() -> tuple[int, int]:
    val = SteamConfig.get_config("AutoDiscoveryQueueTime").data
    try:
        if isinstance(val, (tuple, list)) and len(val) >= 2:
            h, m = int(val[0]), int(val[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h, m
        elif isinstance(val, str) and ":" in val:
            parts = val.strip().split(":")
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h, m
    except Exception:
        pass
    return 2, 0


_explore_h, _explore_m = _parse_discovery_queue_time()


@scheduler.scheduled_job(
    "cron",
    hour=_explore_h,
    minute=_explore_m,
)
async def auto_discovery_queue_job():
    from ..SteamASFDiscoveryQueue.discovery_service import run_auto_discovery_queue_job
    await run_auto_discovery_queue_job()

