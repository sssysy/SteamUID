"""Steam 榜单命令：热门排行与热销排行。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .charts_services import build_hot_chart, build_sale_chart
from ..utils.helper.command import command_guard

charts_sv = SV("steam榜单相关")

# 句中占位型：整串匹配，避免吃掉「排行」等既有命令
_HOT_PATTERN = r"^(?P<period>本周|当前)热门排行$"
_SALE_PATTERN = r"^(?P<period>上周|本周)热销排行$"


@charts_sv.on_regex(_HOT_PATTERN, block=True)
@command_guard
async def steam_hot_chart(bot: Bot, ev: Event) -> None:
    """steam(本周|当前)热门排行：热门游戏 3×3 封面宫格。"""
    await bot.send(MessageSegment.image(await build_hot_chart(ev.regex_dict["period"])))


@charts_sv.on_regex(_SALE_PATTERN, block=True)
@command_guard
async def steam_sale_chart(bot: Bot, ev: Event) -> None:
    """steam(上周|本周)热销排行：热销游戏 3×3 封面宫格。"""
    await bot.send(MessageSegment.image(await build_sale_chart(ev.regex_dict["period"])))
