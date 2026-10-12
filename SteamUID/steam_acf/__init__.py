"""steam更新acf 命令注册。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .acf_services import process_acf_update
from ..utils.helper.command import command_guard

acf_sv = SV("steam更新acf")


@acf_sv.on_fullmatch(("更新acf", "更新manifest"), block=True)
@command_guard
async def steam_update_acf(bot: Bot, ev: Event) -> None:
    """steam更新acf / steam更新manifest：把上传的 appmanifest 伪造为最新版本并回传。"""
    await process_acf_update(bot, ev)
