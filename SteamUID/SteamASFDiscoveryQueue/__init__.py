import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.exceptions import SteamError
from . import discovery_service

discovery_sv = SV("ASF探索队列")


@discovery_sv.on_command("探索队列")
async def steamasf_discovery_queue(bot: Bot, ev: Event):
    """通过 ASF (ASFEnhance) 自动执行 Steam 探索队列"""
    try:
        msg = await discovery_service.run_discovery_queue(ev, ev.text)
        await bot.send(msg)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFDiscoveryQueue] 探索队列命令异常: {e!r}")
        await bot.send("探索队列发生未知错误，详情请查看后台。")
