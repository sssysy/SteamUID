"""Steam 探索队列命令与每日自动探索的定时任务注册。"""

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..steam_config import SteamConfig
from .explore_services import (
    run_manual_queue,
    toggle_auto_queue,
    run_auto_queue_job,
)
from ..utils.helper.command import command_guard

explore_sv = SV("Steam探索队列")

# 键就是整条命令词；值表示开启还是关闭
_AUTO_CMDS: dict[str, bool] = {"开启自动探索队列": True, "关闭自动探索队列": False}


@explore_sv.on_fullmatch("探索队列", block=True)
@command_guard
async def steam_discovery_queue(bot: Bot, ev: Event) -> None:
    """steam探索队列：立即对名下全部账号执行一次探索队列。"""
    await run_manual_queue(bot, ev)


@explore_sv.on_fullmatch(tuple(_AUTO_CMDS), block=True)
@command_guard
async def steam_toggle_auto_queue(bot: Bot, ev: Event) -> None:
    """steam开启自动探索队列 / steam关闭自动探索队列：开关该用户的每日自动探索。"""
    await toggle_auto_queue(bot, ev, enable=_AUTO_CMDS[ev.command])


_QUEUE_HOUR, _QUEUE_MINUTE = SteamConfig.get_config("AutoQueueTime").data


@scheduler.scheduled_job("cron", hour=_QUEUE_HOUR, minute=_QUEUE_MINUTE)
async def auto_queue_job() -> None:
    await run_auto_queue_job()
