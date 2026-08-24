from datetime import datetime

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV, get_plugin_available_prefix
from gsuid_core.segment import MessageSegment
from gsuid_core.logger import logger

from ..utils.api import get_user_Summaries
from .review_service import get_user_year_in_review_share_images
from ..utils.utils import resolve_target_steamid64
from ..utils.exceptions import SteamValidationError, SteamAPIError


year_review_sv = SV("steam年度回顾相关")


def _get_usage_msg() -> str:
    prefix = get_plugin_available_prefix("SteamUID")
    return f"[SteamUID] 参数错误！正确用法：{prefix}年度回顾 [年份]\n如: {prefix}年度回顾2025"


def _parse_args(text: str) -> tuple[str | None, int]:
    """解析用户输入参数，返回 (raw_id, year)。"""
    tokens = text.split()
    default_year = datetime.now().year - 1

    if len(tokens) == 0:
        return None, default_year
    elif len(tokens) == 1:
        t = tokens[0]
        if len(t) == 4 and t.isdigit():
            return None, int(t)
        return t, default_year
    elif len(tokens) == 2:
        t1, t2 = tokens[0], tokens[1]
        t1_is_year = len(t1) == 4 and t1.isdigit()
        t2_is_year = len(t2) == 4 and t2.isdigit()
        if t1_is_year and not t2_is_year:
            return t2, int(t1)
        elif t2_is_year and not t1_is_year:
            return t1, int(t2)
        raise SteamValidationError(_get_usage_msg())
    else:
        raise SteamValidationError(_get_usage_msg())


@year_review_sv.on_command("年度回顾")
async def get_year_review(bot: Bot, ev: Event):
    try:
        usage_msg = _get_usage_msg()
        raw_id, year = _parse_args(ev.text.strip())

        if year < 2022:
            raise SteamValidationError(usage_msg)

        # 解析目标 steamid64（支持 @他人、好友码/SteamID 输入与默认已绑定账号）
        steamid64 = await resolve_target_steamid64(ev, raw_id or "")
        if not steamid64:
            raise SteamValidationError("请先绑定 steam 账号，或输入 好友码/SteamID")

        # 调用 API 获取年度回顾分享图片直链列表
        image_urls = await get_user_year_in_review_share_images(steamid64, year)
        if not image_urls:
            steamuser = steamid64
            try:
                players = await get_user_Summaries(steamid64)
                if players and players[0].get("personaname"):
                    steamuser = players[0]["personaname"]
            except Exception:
                pass
            await bot.send(f"[SteamUID] {steamuser} 的 {year} 年年度回顾未公开")
            return

        # 分别发送获取到的所有年度回顾图片直链
        send_img = []
        for url in image_urls:
            send_img.append(MessageSegment.image(url))
        await bot.send(send_img)

    except SteamValidationError as e:
        await bot.send(str(e))
    except SteamAPIError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamYearReview] 年度回顾命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")

