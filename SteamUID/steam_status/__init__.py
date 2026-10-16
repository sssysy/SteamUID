"""Steam 用户状态查询命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import SteamConfig
from .status_services import build_status_image
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.command import command_guard, resolve_target
from .group_status_services import build_group_status_image

status_sv = SV("steam用户相关")


@status_sv.on_command("状态", block=True)
@command_guard
async def steam_status(bot: Bot, ev: Event) -> None:
    """steam状态[@他人|个人资料页|steamid|好友码]：渲染目标账号的迷你资料卡。"""
    user_id, steamid64 = await resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send(MessageSegment.image(await build_status_image(steamid64)))


@status_sv.on_command("群友状态", block=True)
@command_guard
async def steam_group_status(bot: Bot, ev: Event) -> None:
    """steam群友状态：本群已绑定群友的实时在线与游戏状态。"""
    await bot.send(MessageSegment.image(await build_group_status_image(ev)))
