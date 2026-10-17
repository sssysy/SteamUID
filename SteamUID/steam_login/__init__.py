"""Steam 扫码登录命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .login_services import start_qr_login
from ..utils.helper.command import command_guard_at

login_sv = SV("Steam登录")


@login_sv.on_fullmatch("登录", block=True)
@command_guard_at
async def steam_login(bot: Bot, ev: Event) -> None:
    """扫码登录：发送二维码并等待手机端确认。"""
    await start_qr_login(bot, ev)
