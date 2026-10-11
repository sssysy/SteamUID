"""Steam 成就轮询的定时任务注册。"""

import asyncio

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

from ..steam_config import get_achievement_interval
from .achievement_services import poll_achievements_once

_TAG = "[Steam·成就轮询]"

# 上一轮未结束时跳过本轮，避免慢接口把轮询叠起来
_poll_lock = asyncio.Lock()


@scheduler.scheduled_job("interval", seconds=get_achievement_interval())
async def poll_achievements_job() -> None:
    if _poll_lock.locked():
        logger.debug(f"{_TAG} 上一轮尚未结束，跳过本轮")
        return
    async with _poll_lock:
        await poll_achievements_once()
