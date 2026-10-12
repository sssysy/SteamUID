"""Steam 排行命令：个人 / 群玩家 / 群游戏 / 群游戏玩家 四种游玩时长排行。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import SteamConfig
from .ranking_services import (
    build_self_ranking,
    build_group_game_ranking,
    build_group_player_ranking,
    build_group_game_player_ranking,
)
from ..utils.helper.command import command_guard

ranking_sv = SV("steam排行相关")


@ranking_sv.on_command(("排行", "排名", "统计"), block=True)
@command_guard
async def steam_ranking(bot: Bot, ev: Event) -> None:
    """steam排行[steamid/好友码] [条数]：目标在本群的游戏时长排行。"""
    await bot.send("正在生成排行卡片......")
    await bot.send(MessageSegment.image(await build_self_ranking(ev, allow_at=SteamConfig.get_config("AllowAt").data)))


@ranking_sv.on_command(("群玩家排行", "群玩家排名", "群玩家统计"), block=True)
@command_guard
async def steam_group_player_ranking(bot: Bot, ev: Event) -> None:
    """steam群玩家排行[条数]：按群内用户累计游玩时长排行。"""
    await bot.send("正在生成排行卡片......")
    await bot.send(MessageSegment.image(await build_group_player_ranking(ev)))


@ranking_sv.on_command(("群游戏排行", "群游戏排名", "群游戏统计"), block=True)
@command_guard
async def steam_group_game_ranking(bot: Bot, ev: Event) -> None:
    """steam群游戏排行[条数]：按群内所有游戏累计时长排行。"""
    await bot.send("正在生成排行卡片......")
    await bot.send(MessageSegment.image(await build_group_game_ranking(ev)))


@ranking_sv.on_command(("群游戏玩家排行", "群游戏玩家排名", "群游戏玩家统计"), block=True)
@command_guard
async def steam_group_game_player_ranking(bot: Bot, ev: Event) -> None:
    """steam群游戏玩家排行<游戏名/AppID> [条数]：按该游戏群内玩家时长排行。"""
    await bot.send("正在生成排行卡片......")
    await bot.send(MessageSegment.image(await build_group_game_player_ranking(ev)))
