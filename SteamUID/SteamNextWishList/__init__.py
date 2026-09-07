# -*- coding: utf-8 -*-
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .wishlist_service import add_game_to_wishlist, remove_game_from_wishlist
from ..utils.exceptions import SteamError

next_wishlist_sv = SV("SteamNext愿望单")


@next_wishlist_sv.on_command(("增加愿望单", "添加愿望单"), block=True)
async def handle_add_wishlist(bot: Bot, ev: Event):
    """增加/添加愿望单游戏"""
    try:
        msg = await add_game_to_wishlist(bot, ev)
        await bot.send(msg)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamNextWishList] 添加愿望单执行异常: {e}")
        await bot.send("添加愿望单发生未知错误，详情请查看后台日志。")


@next_wishlist_sv.on_command(("删除愿望单", "移除愿望单", "移出愿望单"), block=True)
async def handle_remove_wishlist(bot: Bot, ev: Event):
    """删除/移除愿望单游戏"""
    try:
        msg = await remove_game_from_wishlist(bot, ev)
        await bot.send(msg)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamNextWishList] 移除愿望单执行异常: {e}")
        await bot.send("移除愿望单发生未知错误，详情请查看后台日志。")
