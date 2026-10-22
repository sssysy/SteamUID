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


@recent_sv.on_command(
    "最近游玩",
    block=True,
    to_ai="""查询 Steam 账号最近两周的游玩记录，并按游玩时长排序。
当用户询问自己最近在玩什么、最近两周玩了哪些游戏或各游戏时长时调用。

Args:
    text: 可选的目标账号，填写个人资料页、SteamID 或好友码。
          留空时查询当前会话中用户已绑定的主账号。
""",
    covers=["Steam 账号最近两周游玩记录、游戏时长排行"],
    aliases=["Steam·最近在玩什么", "Steam·近两周游玩时长", "Steam·最近游玩记录"],
)
@command_guard
async def steam_recent_play(bot: Bot, ev: Event) -> None:
    """steam最近游玩[@他人|个人资料页|steamid|好友码]：按近两周游玩时长渲染排行卡片。"""
    user_id, steamid64 = await resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send(MessageSegment.image(await build_recent_play(steamid64)))
