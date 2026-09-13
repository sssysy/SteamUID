from typing import List, Optional, Union

from gsuid_core.bot import Bot
from gsuid_core.gss import gss
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.message_models import ButtonType


async def send_to_bind(
    bind,
    reply: Optional[
        Union[
            Message,
            List[Message],
            List[str],
            str,
            bytes,
        ]
    ] = None,
    option_list: Optional[ButtonType] = None,
    unsuported_platform: bool = False,
    sep: str = "\n",
    command_tips: str = "请输入以下命令之一:",
    command_start_text: str = "",
    force_direct: bool = False,
):
    user_type = "direct" if force_direct else bind.user_type
    ev = Event(
        bot_id=bind.bot_id,
        user_id=bind.user_id,
        bot_self_id=bind.bot_self_id,
        user_type=user_type,
        group_id=bind.group_id,
        real_bot_id=bind.bot_id,
        msg_id="",
    )
    params = {
        "reply": reply,
        "option_list": option_list,
        "unsuported_platform": unsuported_platform,
        "sep": sep,
        "command_tips": command_tips,
        "command_start_text": command_start_text,
    }

    if bind.WS_BOT_ID:
        if bind.WS_BOT_ID in gss.active_bot:
            BOT = gss.active_bot[bind.WS_BOT_ID]
            bot = Bot(BOT, ev)
            await bot.send_option(**params)
        else:
            logger.error(f"[SteamBind] 机器人{bind.WS_BOT_ID}不存在, 该消息无法发送!")
            return -1
    else:
        for bot_id in gss.active_bot:
            BOT = gss.active_bot[bot_id]
            bot = Bot(BOT, ev)
            await bot.send_option(**params)
