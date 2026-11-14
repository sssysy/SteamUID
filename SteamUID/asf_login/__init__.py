"""ASF 扫码登录命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .login_services import start_asf_login
from ..utils.helper.command import command_guard_at

asf_login_sv = SV("ASF登录")


@asf_login_sv.on_fullmatch("asf登录", block=True)
@command_guard_at
async def steam_asf_login(bot: Bot, ev: Event) -> None:
    """ASF 扫码登录：确认风险后创建 bot、写安全配置并等待扫码。"""
    await start_asf_login(bot, ev)
