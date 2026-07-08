from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..SteamConfig import SteamConfig
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.utils import auto2steamid64
from . import login
from .bind_service import do_bind, do_unbind, format_bind_list, switch_main_id

bind_sv = SV("绑定账号")


@bind_sv.on_command(("绑定", "登录", "登陆", "bind"))
async def steambind(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        steamid64 = auto2steamid64(text)
        if steamid64:
            if SteamConfig.get_config("OnlyOpenID").data:
                raise SteamValidationError("仅允许网页登录，不支持手动绑定steamid！")
        else:
            steamid64 = await login.request_openid_login(bot, ev)
        if steamid64:
            success_msg, warning = await do_bind(ev, steamid64)
            await bot.send(success_msg, True)
            if warning:
                await bot.send(warning)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 绑定命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")


@bind_sv.on_command(("解绑", "unbind", "退出登录", "退出登陆"))
async def steamunbind(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        steamid64 = auto2steamid64(text)
        if not steamid64:
            await bot.send("请在接下来登录一次要解绑的 steam 以继续")
            steamid64 = await login.request_openid_login(bot, ev)
        if steamid64:
            msg = await do_unbind(ev, steamid64)
            await bot.send(msg)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 解绑命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")


@bind_sv.on_command("查看")
async def steamview(bot: Bot, ev: Event):
    try:
        at = ev.at
        if at:
            ev.user_id = at
        show_all = ev.text.strip() == "全部"
        send_msg = await format_bind_list(
            ev.bot_id, ev.user_id, ev.user_type, show_all, ev.group_id
        )
        if send_msg is None:
            await bot.send("未绑定任何 steamid")
        else:
            await bot.send(send_msg)

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 查看命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")


@bind_sv.on_command("切换")
async def switchsteamid(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        steamid64 = auto2steamid64(text)
        if not steamid64:
            raise SteamValidationError("请输入正确的steamid或好友码")
        msg = await switch_main_id(ev, steamid64)
        await bot.send(msg)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 切换命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")
