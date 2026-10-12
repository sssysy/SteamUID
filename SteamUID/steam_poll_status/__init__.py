"""Steam 用户状态轮询的定时任务注册。"""

import asyncio

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

from ..steam_config import SteamConfig
from .status_services import poll_status_once

_TAG = "[Steam·状态轮询]"

# 上一轮未结束时跳过本轮，避免慢接口把轮询叠起来
_poll_lock = asyncio.Lock()


@scheduler.scheduled_job("interval", seconds=SteamConfig.get_config("PollInterval").data)
async def poll_user_status_job() -> None:
    if _poll_lock.locked():
        logger.debug(f"{_TAG} 上一轮尚未结束，跳过本轮")
        return
    async with _poll_lock:
        await poll_status_once()
