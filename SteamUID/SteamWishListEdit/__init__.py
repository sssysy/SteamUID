from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .wishlist_service import add_game_to_wishlist, remove_game_from_wishlist
from ..utils.helpers.command import steam_command

wishlist_edit_sv = SV("Steam愿望单增删")


@steam_command("SteamWishListEdit", fallback="添加愿望单发生未知错误，详情请查看后台日志。")
@wishlist_edit_sv.on_command(("增加愿望单", "添加愿望单"), block=True)
async def handle_add_wishlist(bot: Bot, ev: Event):
    """增加/添加愿望单游戏"""
    msg = await add_game_to_wishlist(bot, ev)
    await bot.send(msg)


@steam_command("SteamWishListEdit", fallback="移除愿望单发生未知错误，详情请查看后台日志。")
@wishlist_edit_sv.on_command(("删除愿望单", "移除愿望单", "移出愿望单"), block=True)
async def handle_remove_wishlist(bot: Bot, ev: Event):
    """删除/移除愿望单游戏"""
    msg = await remove_game_from_wishlist(bot, ev)
    await bot.send(msg)
