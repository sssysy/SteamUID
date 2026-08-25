from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..SteamBind import _send_bind_card
from ..SteamBind.bind_service import do_bind, do_unbind
from ..utils.database.models import SteamBind
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.utils import auto2steamid64, maybe_hide_steamid
from . import login
from .asf_client import ASFClient

asf_sv = SV("ASF登录")


@asf_sv.on_command(("asf登录", "asf登陆", "asf绑定"))
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


@asf_sv.on_command((
    "asf退出登录",
    "asf退出登陆",
    "asf解绑",
    "asf解除绑定"
))
async def steamasf_unbind(bot: Bot, ev: Event):
    """仅退出 ASF 登录并重置 ASF 状态，不影响基础 steamid 绑定"""
    try:
        text = ev.text.strip()
        steamid64 = auto2steamid64(text) if text else None

        if not steamid64:
            # 尝试获取当前群的主账号
            steamid64 = await SteamBind.get_main_id(
                bot_id=ev.bot_id,
                user_id=ev.user_id,
                user_type=ev.user_type,
                group_id=ev.group_id,
            )

        if not steamid64:
            # 如果没有主账号，查看该用户在当前群或全局是否唯一绑定了账号
            user_binds = await SteamBind.get_binds_by_user(
                bot_id=ev.bot_id,
                user_id=ev.user_id,
                user_type=ev.user_type,
                group_id=ev.group_id,
            )
            if not user_binds:
                user_binds = await SteamBind.get_binds_by_user(
                    bot_id=ev.bot_id,
                    user_id=ev.user_id,
                    user_type=ev.user_type,
                )
            if len(user_binds) == 1:
                steamid64 = user_binds[0].steamid64

        if not steamid64:
            await bot.send("未找到当前账号的默认主账号绑定，请在命令后附带要退出的账号参数，例如：\nasf退出登录 [steam好友码]")
            return

        # 1. 调用 ASF IPC 删除/停止该用户的 Bot 实例
        bot_name = login._sanitize_bot_name(ev.user_id)
        await ASFClient.delete_bot(bot_name)

        # 2. 清除数据库中的 is_asf 标记，不影响基础绑定
        await SteamBind.unmark_asf(
            steamid64=steamid64,
            bot_id=ev.bot_id,
            user_id=ev.user_id,
            user_type=ev.user_type,
        )

        success_msg = f"已成功退出 Steam ({maybe_hide_steamid(steamid64)}) 的 ASF 登录并清除 ASF 记录！"
        await _send_bind_card(
            bot, ev, fallback_msg=success_msg, show_all=True
        )

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFLogin] ASF退出登录异常: {e!r}")
        await bot.send("ASF退出登录过程发生未知错误，详情请查看后台。")
