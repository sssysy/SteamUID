# -*- coding: utf-8 -*-
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .queue_service import handle_user_discovery_queue

queue_sv = SV("Steam探索队列")


@queue_sv.on_command(("探索队列", "steam探索队列"), block=True)
async def discovery_queue_cmd(bot: Bot, ev: Event):
    """手动执行 Steam 探索队列"""
    try:
        await handle_user_discovery_queue(bot, ev)
    except Exception as e:
        logger.exception(f"[SteamDiscoveryQueue] 探索队列执行异常: {e}")
        await bot.send("探索队列执行发生未知错误，详情请查看后台日志。")
