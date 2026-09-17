from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.helpers.command import steam_command
from .acf_service import process_acf_update

acf_SV = SV("steam更新acf")


@steam_command("SteamAcf")
@acf_SV.on_fullmatch(("更新acf", "更新manifest"), block=True)
async def steam_update_acf(bot: Bot, ev: Event):
    await process_acf_update(bot, ev)
