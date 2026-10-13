"""Steam 年度回顾命令：发送官方生成的年度回顾分享图。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..steam_config import SteamConfig
from ..utils.helper.bind import get_main_steamid64
from .year_review_services import parse_year, fetch_year_review_images
from ..utils.helper.command import command_guard, resolve_viewer

year_review_sv = SV("steam年度回顾相关")


@year_review_sv.on_command(("年度回顾", "年度报告"), block=True)
@command_guard
async def steam_year_review(bot: Bot, ev: Event) -> None:
    """steam年度回顾[年份]：发送该账号指定年份的 Steam 官方年度回顾分享图。"""
    year = parse_year(ev.text)
    user_id = resolve_viewer(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    images = await fetch_year_review_images(steamid64, year)
    if not images:
        await bot.send(f"未找到该账号 {year} 年的公开年度回顾")
        return
    await bot.send([MessageSegment.image(path) for path in images])
