"""Steam 游戏墙命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import get_allow_at
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.command import command_guard, resolve_target
from .library_services import build_game_wall

library_sv = SV("steam库存相关")


@library_sv.on_command("游戏墙", block=True)
@command_guard
async def steam_game_wall(bot: Bot, ev: Event) -> None:
    """steam游戏墙：把目标账号的游戏库渲染成封面墙。"""
    user_id, steamid64 = resolve_target(ev, allow_at=get_allow_at())
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send("正在制作游戏墙......")
    await bot.send(MessageSegment.image(await build_game_wall(steamid64)))
