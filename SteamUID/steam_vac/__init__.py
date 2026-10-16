"""Steam 封禁查询命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .vac_services import build_ban_text
from ..steam_config import SteamConfig
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.command import command_guard, resolve_target

vac_sv = SV("steam用户相关")


@vac_sv.on_command(("vac", "查封禁"), block=True)
@command_guard
async def steam_vac(bot: Bot, ev: Event) -> None:
    """steamvac / steam查封禁[@他人|个人资料页|steamid|好友码]：查询目标账号的封禁汇总。"""
    user_id, steamid64 = await resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    await bot.send(await build_ban_text(steamid64))
