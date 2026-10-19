"""Steam 价格订阅命令：降价 / 史低模式、取消订阅与列表出图。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .price_services import (
    subscribe_price,
    subscribe_history,
    unsubscribe_price,
    unsubscribe_history,
    build_price_list_card,
)
from ..utils.helper.command import command_guard

price_sv = SV("Steam降价订阅")


async def _send_price_list(bot: Bot, ev: Event) -> None:
    """出价格订阅列表卡片。"""
    await bot.send(MessageSegment.image(await build_price_list_card(ev)))


@price_sv.on_fullmatch(("订阅降价查看", "订阅史低查看"), block=True)
@command_guard
async def steam_price_list(bot: Bot, ev: Event) -> None:
    """steam订阅降价查看：本会话订阅模式与当前售价。"""
    await _send_price_list(bot, ev)


# 前缀允许命令词后不带空格，订阅降价查看 会被 订阅降价 先吃掉，故前缀内转出列表
@price_sv.on_prefix("订阅降价", block=True)
@command_guard
async def steam_price_subscribe(bot: Bot, ev: Event) -> None:
    """steam订阅降价<游戏名/AppID>：订阅该游戏的降价提醒。"""
    if ev.text.strip() == "查看":
        await _send_price_list(bot, ev)
        return
    await subscribe_price(bot, ev)


@price_sv.on_prefix("订阅史低", block=True)
@command_guard
async def steam_history_subscribe(bot: Bot, ev: Event) -> None:
    """steam订阅史低<游戏名/AppID>：订阅或覆盖为史低提醒。"""
    if ev.text.strip() == "查看":
        await _send_price_list(bot, ev)
        return
    await subscribe_history(bot, ev)


@price_sv.on_prefix("取消订阅降价", block=True)
@command_guard
async def steam_price_unsubscribe(bot: Bot, ev: Event) -> None:
    """steam取消订阅降价<游戏名/AppID>：取消订阅该游戏的降价提醒。"""
    await unsubscribe_price(bot, ev)


@price_sv.on_prefix("取消订阅史低", block=True)
@command_guard
async def steam_history_unsubscribe(bot: Bot, ev: Event) -> None:
    """steam取消订阅史低<游戏名/AppID>：取消订阅该游戏的史低提醒。"""
    await unsubscribe_history(bot, ev)
