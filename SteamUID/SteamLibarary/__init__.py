import random
from io import BytesIO

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment, pic_quality
from gsuid_core.sv import SV

from ..SteamConfig import SteamConfig
from ..SteamConfig.interface import SteamAPI
from ..utils.api import get_steamlibrary_by_steamid64
from ..utils.downloader import download
from ..utils.exceptions import (
    SteamConfigError,
    SteamError,
    SteamValidationError,
)
from ..utils.PIL.draw import draw_what_to_play
from ..utils.PIL.steam_wall import build_wall
from ..utils.utils import resolve_target_steamid64

library_SV = SV("steam库存相关")


async def build_library_wall(steamid64: str) -> bytes:
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    library = await get_steamlibrary_by_steamid64(api_key, steamid64)
    if library.get("games") is None:
        raise SteamValidationError("获取 steam 游戏库列表失败")

    gameinfo = []
    cdn_urls = []
    played_times = []
    for game in library.get("games", []):
        appid = game.get("appid")
        url = SteamAPI.GetGameCoverImageURL(appid, variant='library_600x900')
        cdn_urls.append(url)
        played_time = (
            game.get("playtime_forever", 0) or
            game.get("playtime_windows_forever", 0) +
            game.get("playtime_mac_forever", 0) +
            game.get("playtime_linux_forever", 0) +
            game.get("playtime_deck_forever", 0)
        )
        played_times.append(played_time)

    downloaded_paths = await download(cdn_urls)
    for i, file_path in enumerate(downloaded_paths):
        gameinfo.append((str(file_path) if file_path is not None else None, played_times[i]))

    if not gameinfo:
        raise SteamValidationError("该 steam 账号暂无游戏库存")

    wall = build_wall(gameinfo)

    buf = BytesIO()
    wall.save(buf, format="JPEG", quality=pic_quality, subsampling=0)
    return buf.getvalue()


async def build_random_pick(steamid64: str) -> bytes:
    """从用户 Steam 游戏库中随机选取 3 款游戏，生成推荐图片。"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    library = await get_steamlibrary_by_steamid64(api_key, steamid64)
    games = library.get("games")
    if games is None:
        raise SteamValidationError("获取 steam 游戏库列表失败")
    if not games:
        raise SteamValidationError("该 steam 账号暂无游戏库存")
    pick_count = min(3, len(games))
    picks = random.sample(games, pick_count)
    game_data = []

    for game in picks:
        appid = str(game.get("appid", ""))
        name = game.get("name", "未知游戏")
        playtime = (
            game.get("playtime_forever", 0) or
            game.get("playtime_windows_forever", 0) +
            game.get("playtime_mac_forever", 0) +
            game.get("playtime_linux_forever", 0) +
            game.get("playtime_deck_forever", 0)
        )
        cover_url = SteamAPI.GetGameCoverImageURL(appid, variant='library_600x900')
        game_data.append({
            "appid": appid,
            "name": name,
            "playtime": playtime,
            "cover_url": cover_url,
        })

    img = await draw_what_to_play(game_data)
    img = img.convert("RGB")

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=pic_quality, subsampling=0)
    return buf.getvalue()


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


@library_SV.on_command("玩什么")
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