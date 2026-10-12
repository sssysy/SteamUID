"""Steam 游戏降价轮询的定时任务注册。"""

import asyncio

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

from ..steam_config import SteamConfig
from .price_services import poll_price_once

_TAG = "[Steam·降价轮询]"

# 上一轮未结束时跳过本轮，避免慢接口把轮询叠起来
_poll_lock = asyncio.Lock()


@scheduler.scheduled_job("interval", hours=SteamConfig.get_config("PricePollInterval").data)
async def poll_price_job() -> None:
    if _poll_lock.locked():
        logger.debug(f"{_TAG} 上一轮尚未结束，跳过本轮")
        return
    async with _poll_lock:
        await poll_price_once()
