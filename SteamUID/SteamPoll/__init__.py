from gsuid_core.aps import scheduler

from ..SteamConfig import SteamConfig
from . import poll_service
from . import cache_poll

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

# steam 缓存清理
@scheduler.scheduled_job(
    'interval',
    days=SteamConfig.get_config("CacheTime").data,
)
async def purge_cache():
    await cache_poll.purge_stale_caches()
