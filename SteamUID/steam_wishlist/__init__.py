"""Steam 愿望单命令：列表出图与愿望单增删。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import get_allow_at
from .wishlist_services import (
    add_wishlist_game,
    build_wishlist_card,
    remove_wishlist_game,
)
from ..utils.helper.command import command_guard

wishlist_sv = SV("steam愿望单相关")


@wishlist_sv.on_command("愿望单列表", block=True)
@command_guard
async def steam_wishlist_list(bot: Bot, ev: Event) -> None:
    """steam愿望单列表[条数]：目标账号的愿望单与当前售价。"""
    await bot.send("正在生成愿望单卡片......")
    await bot.send(MessageSegment.image(await build_wishlist_card(ev, allow_at=get_allow_at())))


@wishlist_sv.on_prefix("增加愿望单", block=True)
@command_guard
async def steam_wishlist_add(bot: Bot, ev: Event) -> None:
    """steam增加愿望单<游戏名/AppID>：把游戏加入自己账号的愿望单。"""
    await add_wishlist_game(bot, ev)


@wishlist_sv.on_prefix("删除愿望单", block=True)
@command_guard
async def steam_wishlist_remove(bot: Bot, ev: Event) -> None:
    """steam删除愿望单<游戏名/AppID>：把游戏移出自己账号的愿望单。"""
    await remove_wishlist_game(bot, ev)
