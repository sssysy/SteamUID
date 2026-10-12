"""Steam CDKey 激活命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .cdkey_services import activate_cdkeys
from ..utils.helper.command import command_guard

cdkey_sv = SV("Steam激活CDKey")


@cdkey_sv.on_command("激活", block=True)
@command_guard
async def steam_activate(bot: Bot, ev: Event) -> None:
    """steam激活<CDKey>：私聊内激活一枚或多枚 CDKey（空格 / 逗号 / 换行分隔）。"""
    await activate_cdkeys(bot, ev)
