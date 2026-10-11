"""Steam 游戏成就查询命令与成就轮询的定时任务注册。"""

import asyncio

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import get_allow_at, get_achievement_interval
from ..utils.helper.bind import get_main_steamid64
from .achievement_services import build_achievement_card, poll_achievements_once
from ..utils.helper.command import command_guard, resolve_viewer

_TAG = "[Steam·成就轮询]"

achievement_sv = SV("steam成就相关")


@achievement_sv.on_command("游戏成就", block=True)
@command_guard
async def steam_game_achievement(bot: Bot, ev: Event) -> None:
    """steam游戏成就<游戏名/AppID>：把当前账号的成就进度渲染成卡片。"""
    user_id = resolve_viewer(ev, allow_at=get_allow_at())
    steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send("正在查询成就......")
    result = await build_achievement_card(steamid64, ev.text)
    if result.hint:
        await bot.send(result.hint)
    await bot.send(MessageSegment.image(result.image))


# 上一轮未结束时跳过本轮，避免慢接口把轮询叠起来
_poll_lock = asyncio.Lock()


@scheduler.scheduled_job("interval", seconds=get_achievement_interval())
async def poll_achievements_job() -> None:
    if _poll_lock.locked():
        logger.debug(f"{_TAG} 上一轮尚未结束，跳过本轮")
        return
    async with _poll_lock:
        await poll_achievements_once()
