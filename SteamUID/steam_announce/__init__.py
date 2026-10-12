"""Steam 公告订阅命令与公告轮询的定时任务注册。"""

import asyncio

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .announce_services import (
    poll_announce_once,
    subscribe_announce,
    unsubscribe_announce,
    build_announce_list_card,
)
from ..utils.helper.command import command_guard

_TAG = "[Steam·公告轮询]"

# 公告更新频率低，固定一小时一轮；需要可调再用配置项替换
_POLL_HOURS = 1

announce_sv = SV("Steam公告订阅")


# 列表整串匹配必须先于 订阅公告 前缀注册，否则会被前缀吃掉参数区
@announce_sv.on_fullmatch("订阅公告列表", block=True)
@command_guard
async def steam_announce_list(bot: Bot, ev: Event) -> None:
    """steam订阅公告列表：本会话本人订阅的游戏公告列表。"""
    await bot.send("正在生成公告订阅列表......")
    await bot.send(MessageSegment.image(await build_announce_list_card(ev)))


@announce_sv.on_prefix("订阅公告", block=True)
@command_guard
async def steam_announce_subscribe(bot: Bot, ev: Event) -> None:
    """steam订阅公告<游戏名/AppID>：订阅该游戏的新公告推送。"""
    await subscribe_announce(bot, ev)


@announce_sv.on_prefix("取消订阅公告", block=True)
@command_guard
async def steam_announce_unsubscribe(bot: Bot, ev: Event) -> None:
    """steam取消订阅公告<游戏名/AppID>：取消订阅该游戏的公告推送。"""
    await unsubscribe_announce(bot, ev)


# 上一轮未结束时跳过本轮，避免慢接口把轮询叠起来
_poll_lock = asyncio.Lock()


@scheduler.scheduled_job("interval", hours=_POLL_HOURS)
async def poll_announce_job() -> None:
    if _poll_lock.locked():
        logger.debug(f"{_TAG} 上一轮尚未结束，跳过本轮")
        return
    async with _poll_lock:
        await poll_announce_once()
