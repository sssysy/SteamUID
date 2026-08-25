from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..SteamBind import _send_bind_card
from ..SteamBind.bind_service import do_bind
from ..utils.exceptions import SteamError
from . import login

asf_sv = SV("ASF登录")


@asf_sv.on_command(("asf登录", "asf登陆", "asf绑定", "asflogin", "asf bind"))
async def steamasf_bind(bot: Bot, ev: Event):
    """通过 ASF 网页登录绑定 Steam 账号"""
    try:
        steamid64 = await login.request_asf_login(bot, ev)
        if steamid64:
            success_msg, warning = await do_bind(ev, steamid64, is_asf=True)
            fallback = success_msg
            if warning:
                fallback += f"\n{warning}"
            await _send_bind_card(
                bot, ev, fallback_msg=fallback, new_bind_steamid=steamid64, show_all=True
            )
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFLogin] ASF登录命令异常: {e!r}")
        await bot.send("ASF登录过程发生未知错误，详情请查看后台。")
