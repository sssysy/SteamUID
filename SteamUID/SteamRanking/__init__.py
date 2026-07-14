from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.database.models import CoreUser

from ..utils.exceptions import SteamError, SteamValidationError
# from ..utils.target import resolve_target_steamid64
from ..utils.utils import time_convert_s
from .ranking_service import get_group_ranking_list, get_game_ranking_list

ranking_sv = SV("steam排名服务")

@ranking_sv.on_command(("群排行", "群排名"))
async def group_ranking(bot: Bot, ev: Event):
    """按用户游戏时长从高到低取5位返回"""
    try:
        if not ev.group_id:
            raise SteamValidationError("请在群聊中使用此功能")

        ranking_list = await get_group_ranking_list(ev.group_id)
        top5 = ranking_list[:5]

        if not top5:
            await bot.send("本群暂无游戏时长排行数据")
            return

        text = f"本群游戏时长排行 Top：{len(top5)}\n"
        for i, item in enumerate(top5, 1):
            users = await CoreUser.select_rows(user_id=item["user_id"], group_id=ev.group_id)
            if users and users[0].user_name:
                name = users[0].user_name
            else:
                name = item["user_id"]

            text += f"{i}. {name} ({time_convert_s(item['total_duration'])})\n"

        await bot.send(text)

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamRanking - 群排行] 未知错误: {e!r}")
        await bot.send("发生未知错误，请联系管理员查看控制台")


@ranking_sv.on_command(("群游戏排行", "群游戏排名"))
async def game_ranking(bot: Bot, ev: Event):
    """按群内所有游戏的总游玩时长从高到低排序"""
    try:
        if not ev.group_id:
            raise SteamValidationError("请在群聊中使用此功能")

        ranking_list = await get_game_ranking_list(ev.group_id)
        top10 = ranking_list[:10]

        if not top10:
            await bot.send("本群暂无游戏时长排行数据")
            return

        text = f"本群游戏时长排行 Top{len(top10)}：\n"
        for i, item in enumerate(top10, 1):
            text += f"{i}. {item['game_name']} ({time_convert_s(item['total_duration'])})\n"

        await bot.send(text)

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamRanking - 群游戏排行] 未知错误: {e!r}")
        await bot.send("发生未知错误，请联系管理员查看控制台")

        
"""
============鸽了=============

@ranking_sv.on_command(("我的排行", "我的排名"))
async def my_ranking(bot: Bot, ev: Event):
    获取用户在群中的排名，应为总排行 + ... + 用户所在排行位置

"""
