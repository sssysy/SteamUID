"""Steam 信息命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import get_allow_at
from .info_services import build_steam_info
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.command import command_guard, resolve_target

info_sv = SV("steam用户相关")


@info_sv.on_command("信息", block=True)
@command_guard
async def steam_info(bot: Bot, ev: Event) -> None:
    """steam信息：渲染目标账号的资料与统计卡片。"""
    user_id, steamid64 = resolve_target(ev, allow_at=get_allow_at())
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send("正在生成信息卡片......")
    await bot.send(MessageSegment.image(await build_steam_info(steamid64)))
