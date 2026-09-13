import asyncio
import html
import random
import re
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..SteamConfig import SteamConfig
from ..SteamConfig.interface import SteamAPI
from ..utils.Api import (
    get_game_cover_url,
    get_game_info,
    get_steamlibrary_by_steamid64,
    get_user_Summaries,
    get_miniprofile,
    get_profile_items_equipped,
    resolve_games_covers,
)
from ..utils.exceptions import (
    SteamConfigError,
    SteamError,
    SteamValidationError,
    SteamAPIError,
)
from ..utils.helpers.game import total_playtime
from ..utils.helpers.profile import resolve_profile_assets
from ..utils.helpers.steam_state import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from ..utils.render import render_game_recommend, render_steam_wall
from ..utils.utils import resolve_target_steamid64, steamid64_to_friend_code
from ..utils.helpers.command import steam_command

library_SV = SV("steam库存相关")


def _clean_description(text: str) -> str:
    """清理 Steam 游戏简介中的 HTML 标签与实体。"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _load_user_library(
    steamid64: str, *, private_msg: str
) -> tuple[dict, list[dict]]:
    """并发拉取用户摘要 + 游戏库，完成全部校验，返回 (user_data, games)。
    """
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    players_res, miniprofile_data, items_data, library_res = await asyncio.gather(
        get_user_Summaries(steamid64),
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        get_steamlibrary_by_steamid64(api_key, steamid64),
        return_exceptions=True,
    )

    if isinstance(players_res, SteamError):
        raise players_res
    if isinstance(library_res, SteamError):
        raise library_res

    if isinstance(players_res, Exception) or not players_res:
        raise SteamAPIError("未找到该 Steam 用户")
    player = players_res[0]

    if isinstance(library_res, Exception) or not isinstance(library_res, dict):
        raise SteamValidationError("获取 steam 游戏库列表失败")

    games = library_res.get("games")
    if games is None:
        visibility = player.get("communityvisibilitystate", VISIBILITY_PUBLIC)
        if visibility == VISIBILITY_PRIVATE:
            raise SteamValidationError(private_msg)
        raise SteamValidationError("获取 steam 游戏库列表失败")
    if not games:
        raise SteamValidationError("该 steam 账号暂无游戏库存")

    assets = await resolve_profile_assets(
        steamid64,
        player=player,
        miniprofile_data=miniprofile_data,
        items_data=items_data,
    )
    user_data = {
        "name": player.get("personaname", "未知用户"),
        "friend_code": steamid64_to_friend_code(steamid64),
        "avatar_url": assets.avatar_url,
        "avatar_frame_url": assets.avatar_frame_url,
        "bg_url": assets.bg_url,
    }
    return user_data, games


async def build_library_wall(steamid64: str) -> bytes:
    """构建 Steam 游戏墙卡片：顶部用户胶囊卡片 + 下方 dense 游戏封面墙"""
    user_data, games = await _load_user_library(
        steamid64, private_msg="该用户资料为私有，无法获取游戏墙"
    )

    # 解析游戏列表
    games_data = [
        {
            "appid": g.get("appid"),
            "name": g.get("name", ""),
            "playtime_forever": total_playtime(g),
        }
        for g in games
    ]

    # 若开启 GridDB 备选，则批量解析/补全封面
    if SteamConfig.get_config("AllowGridDBCover").data:
        await resolve_games_covers(games_data)

    # 调用 Playwright 渲染
    return await render_steam_wall(user_data, games_data, canvas_width=1200)


async def build_random_pick(steamid64: str) -> bytes:
    """从用户 Steam 游戏库中随机选取 3 款正常游戏，生成推荐图片。"""
    user_data, games = await _load_user_library(
        steamid64, private_msg="该用户资料为私有，无法获取游戏库"
    )

    # 随机打乱游戏库列表并选取游戏
    shuffled_games = random.sample(games, len(games))
    valid_games = []

    # 分批并发查询游戏详情（跳过无有效简介或状态异常的游戏）
    batch_size = 6
    for i in range(0, len(shuffled_games), batch_size):
        batch = [g for g in shuffled_games[i:i + batch_size] if g.get("appid")]
        if not batch:
            continue
        appids = [str(g["appid"]) for g in batch]

        results = await asyncio.gather(
            *[get_game_info(aid) for aid in appids],
            return_exceptions=True,
        )

        for game_entry, aid, res in zip(batch, appids, results):
            if isinstance(res, Exception) or not isinstance(res, dict):
                continue
            if not res.get("success") or "data" not in res:
                continue

            data = res.get("data")
            if not isinstance(data, dict):
                continue

            short_desc = data.get("short_description", "")
            clean_desc = _clean_description(short_desc)
            if not clean_desc or len(clean_desc.strip()) < 2:
                # 跳过无有效简介/异常游戏
                continue

            name = data.get("name") or game_entry.get("name") or "未知游戏"
            header_img = await get_game_cover_url(aid, header_image=data.get("header_image"))

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

    return await render_game_recommend(valid_games, user_data=user_data)


@steam_command("steam库存")
@library_SV.on_command(("游戏墙", "游戏库"))
async def get_steamlibrary_image(bot: Bot, ev: Event):
    steamid64 = await resolve_target_steamid64(ev, ev.text.strip())
    if not steamid64:
        raise SteamValidationError("请先绑定 steam 账号")

    await bot.send("正在开始制作封面墙......")
    img_bytes = await build_library_wall(steamid64)
    await bot.send(MessageSegment.image(img_bytes))


@steam_command("steam库存")
@library_SV.on_command("玩什么")
async def get_my_steamlibrary_image(bot: Bot, ev: Event):
    steamid64 = await resolve_target_steamid64(ev, ev.text.strip())
    if not steamid64:
        raise SteamValidationError("请先绑定 steam 账号")

    await bot.send("正在从游戏库中随机挑选......")
    img_bytes = await build_random_pick(steamid64)
    await bot.send(MessageSegment.image(img_bytes))