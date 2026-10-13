"""Steam 当前玩家命令：查询指定游戏当前在线玩家数。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .players_services import query_current_players
from ..utils.helper.command import command_guard

players_sv = SV("Steam当前玩家")


# 长命令词先注册，"当前玩家数 x" 才不会被 "当前玩家" 抢走参数
@players_sv.on_prefix(("当前玩家数", "当前玩家"), block=True)
@command_guard
async def steam_current_players(bot: Bot, ev: Event) -> None:
    """steam当前玩家(数)<游戏名/AppID>：查询该游戏当前在线玩家数。"""
    await query_current_players(bot, ev)
