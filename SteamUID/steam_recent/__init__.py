"""Steam 最近游玩命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import SteamConfig
from .recent_services import build_recent_play
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.command import command_guard, resolve_target

recent_sv = SV("steam最近游玩相关")


@recent_sv.on_command("最近游玩", block=True)
@command_guard
async def steam_recent_play(bot: Bot, ev: Event) -> None:
    """steam最近游玩[@他人|steamid|好友码]：按近两周游玩时长渲染排行卡片。"""
    user_id, steamid64 = resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send(MessageSegment.image(await build_recent_play(steamid64)))
