# -*- coding: utf-8 -*-
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .cdkey_service import handle_cdkey_activation
from ..utils.exceptions import SteamError

cdkey_sv = SV("SteamCDKey")


@cdkey_sv.on_command(("激活", "激活cdk", "兑换", "激活cdkey"), block=True)
async def handle_cdkey_cmd(bot: Bot, ev: Event):
    """Steam CDKey 激活指令"""
    # 强制私聊使用，防止群聊暴露 CDKey
    if ev.user_type != "direct":
        await bot.send("请私聊激活 CDKey 防止 CDKey 被盗用！")
        return

    try:
        await handle_cdkey_activation(bot, ev)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamCDKey] 激活 CDKey 发生未知异常: {e}")
        await bot.send("激活 CDKey 发生未知错误，详情请查看后台日志。")
