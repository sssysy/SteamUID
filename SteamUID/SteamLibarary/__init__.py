from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment

from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.target import resolve_target_steamid64
from .library_service import build_library_wall, build_random_pick

library_SV = SV("steam库存相关")


@library_SV.on_command(("游戏墙", "游戏库"))
async def get_steamlibrary_image(bot: Bot, ev: Event):
    try:
        steamid64 = await resolve_target_steamid64(ev, ev.text.strip())
        if not steamid64:
            raise SteamValidationError("请先绑定 steam 账号")

        await bot.send("正在开始制作封面墙......")
        img_bytes = await build_library_wall(steamid64)
        await bot.send(MessageSegment.image(img_bytes))
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[steam库存] 未知错误: {e!r}")
        await bot.send(f"发生未知错误: {e}")

@library_SV.on_command(("玩什么",))
async def get_my_steamlibrary_image(bot: Bot, ev: Event):
    try:
        steamid64 = await resolve_target_steamid64(ev, ev.text.strip())
        if not steamid64:
            raise SteamValidationError("请先绑定 steam 账号")

        await bot.send("正在从游戏库中随机挑选......")
        img_bytes = await build_random_pick(steamid64)
        await bot.send(MessageSegment.image(img_bytes))
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[steam库存] 未知错误: {e!r}")
        await bot.send(f"发生未知错误: {e}")