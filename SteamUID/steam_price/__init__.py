"""Steam 降价订阅命令：订阅 / 取消订阅 / 订阅列表出图。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .price_services import (
    subscribe_price,
    unsubscribe_price,
    build_price_list_card,
)
from ..utils.helper.command import command_guard

price_sv = SV("Steam降价订阅")


# 列表整串匹配必须先于 订阅降价 前缀注册，否则会被前缀吃掉参数区
@price_sv.on_fullmatch("订阅降价查看", block=True)
@command_guard
async def steam_price_list(bot: Bot, ev: Event) -> None:
    """steam订阅降价查看：本会话本人订阅的降价提醒与当前售价。"""
    await bot.send("正在生成降价订阅列表......")
    await bot.send(MessageSegment.image(await build_price_list_card(ev)))


@price_sv.on_prefix("订阅降价", block=True)
@command_guard
async def steam_price_subscribe(bot: Bot, ev: Event) -> None:
    """steam订阅降价<游戏名/AppID>：订阅该游戏的降价提醒。"""
    await subscribe_price(bot, ev)


@price_sv.on_prefix("取消订阅降价", block=True)
@command_guard
async def steam_price_unsubscribe(bot: Bot, ev: Event) -> None:
    """steam取消订阅降价<游戏名/AppID>：取消订阅该游戏的降价提醒。"""
    await unsubscribe_price(bot, ev)
