from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment

from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.target import resolve_target_steamid64
from .achievement_service import fetch_achievement_lists, render_achievement_image

SV = SV("steam成就服务")


@SV.on_command("游戏成就")
async def game_archivements(bot: Bot, ev: Event):
    appid = ev.text.strip()
    try:
        if not appid:
            raise SteamValidationError("请携带appid！")
        steamid64 = await resolve_target_steamid64(ev)
        if not steamid64:
            raise SteamValidationError("请先绑定 steam 账号")

        data = await fetch_achievement_lists(appid, steamid64)
        img = await render_achievement_image(
            data["game_name"], data["unlocked"], data["locked"], steamid64
        )
        await bot.send(MessageSegment.image(img))

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[steamUID - 游戏成就] 未知错误 appid={appid}: {e!r}")
        await bot.send(f"发生未知错误: {e}")
