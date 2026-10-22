"""Steam 信息命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import SteamConfig
from .info_services import build_steam_info, build_identity_text
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.command import command_guard, resolve_target

info_sv = SV("steam用户相关")


@info_sv.on_command("信息", block=True)
@command_guard
async def steam_info(bot: Bot, ev: Event) -> None:
    """steam信息[@他人|个人资料页|steamid|好友码]：渲染目标账号的资料与统计卡片。"""
    user_id, steamid64 = await resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send(MessageSegment.image(await build_steam_info(steamid64)))


@info_sv.on_command(
    "转换",
    block=True,
    to_ai="""将 Steam 个人资料页、SteamID 或好友码转换为 SteamID64、SteamID3、好友码等身份格式。
当用户要求 Steam 好友码、账号链接或 SteamID 互转，或需要确认某个 Steam 账号的多种 ID 时调用。

Args:
    text: 个人资料页 URL、SteamID64、SteamID3、好友码或自定义社区 URL。
          例如 "好友码"、"https://steamcommunity.com/id/自定义ID"。
""",
    covers=["Steam 身份格式互转：SteamID64、SteamID3、好友码、个人资料页、自定义社区 URL"],
    aliases=["Steam·账号ID互转", "Steam·好友码转SteamID64", "Steam·个人资料链接解析"],
)
@command_guard
async def steam_convert(bot: Bot, ev: Event) -> None:
    """steam转换<个人资料页|steamid|好友码>：输出账号的多格式身份信息。"""
    await bot.send(await build_identity_text(ev.text))
