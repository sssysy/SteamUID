import asyncio
import html
import random
import re
from io import BytesIO

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment, pic_quality
from gsuid_core.sv import SV

from ..SteamConfig import SteamConfig
from ..SteamConfig.interface import SteamAPI
from ..utils.api import get_game_info, get_steamlibrary_by_steamid64
from ..utils.downloader import download
from ..utils.exceptions import (
    SteamConfigError,
    SteamError,
    SteamValidationError,
)
from ..utils.PIL.steam_wall import build_wall
from ..utils.render import render_game_recommend
from ..utils.utils import resolve_target_steamid64

library_SV = SV("steam库存相关")


def _clean_description(text: str) -> str:
    """清理 Steam 游戏简介中的 HTML 标签与实体。"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
    """从用户 Steam 游戏库中随机选取 3 款正常游戏，生成推荐图片。"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    library = await get_steamlibrary_by_steamid64(api_key, steamid64)
    games = library.get("games")
    if games is None:
        raise SteamValidationError("获取 steam 游戏库列表失败")
    if not games:
        raise SteamValidationError("该 steam 账号暂无游戏库存")

    # 随机打乱游戏库列表
    shuffled_games = random.sample(games, len(games))
    valid_games = []

    # 分批并发查询游戏详情（跳过无有效简介或状态异常的游戏）
    batch_size = 6
    for i in range(0, len(shuffled_games), batch_size):
        batch = shuffled_games[i:i + batch_size]
        appids = [str(g.get("appid", "")) for g in batch if g.get("appid")]

        results = await asyncio.gather(
            *[get_game_info(aid) for aid in appids],
            return_exceptions=True,
        )

        for game_entry, aid, res in zip(batch, appids, results):
            if isinstance(res, Exception) or not isinstance(res, dict):
                continue
            if not res.get("success") or "data" not in res:
                continue

            data = res.get("data", {})
            short_desc = data.get("short_description", "")
            clean_desc = _clean_description(short_desc)
            if not clean_desc or len(clean_desc.strip()) < 2:
                # 跳过无有效简介/异常游戏
                continue

            name = data.get("name") or game_entry.get("name") or "未知游戏"
            header_img = data.get("header_image") or SteamAPI.GetGameCoverImageURL(aid, variant="header")

            valid_games.append({
                "appid": aid,
                "name": name,
                "description": clean_desc,
                "cover_url": header_img,
            })

            if len(valid_games) >= 3:
                break

        if len(valid_games) >= 3:
            break

    if not valid_games:
        raise SteamValidationError("未能在游戏库中找到可推荐的有效游戏")

    return await render_game_recommend(valid_games)


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