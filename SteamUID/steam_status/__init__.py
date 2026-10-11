"""Steam 用户状态查询命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import get_allow_at
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.command import command_guard, resolve_target
from .status_services import build_status_image

status_sv = SV("steam用户相关")


@status_sv.on_command("状态", block=True)
@command_guard
async def steam_status(bot: Bot, ev: Event) -> None:
    """steam状态[@他人|steamid|好友码]：渲染目标账号的迷你资料卡。"""
    user_id, steamid64 = resolve_target(ev, allow_at=get_allow_at())
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send("正在查询状态......")
    await bot.send(MessageSegment.image(await build_status_image(steamid64)))
