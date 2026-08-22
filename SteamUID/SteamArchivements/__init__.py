import asyncio
from datetime import datetime, timezone, timedelta

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..utils.api import (
    get_archivement_info,
    get_archivement_schema,
    get_game_info,
    get_game_icon_url,
    get_user_Summaries,
    get_miniprofile,
    get_profile_items_equipped,
)
from ..utils.exceptions import (
    SteamError,
    SteamRenderError,
    SteamValidationError,
)
from ..utils.render import render_steam_achievement
from ..utils.utils import resolve_target_appid, resolve_target_steamid64, steamid64_to_friend_code

SV = SV("steam成就服务")


async def build_achievement_data(
    appid: str, steamid64: str
) -> tuple[dict, dict, list[dict]]:
    # 并发获取成就、Schema、游戏信息、用户信息、游戏小Logo
    tasks = [
        get_archivement_info(appid, steamid64),
        get_archivement_schema(appid),
        get_game_info(appid),
        get_user_Summaries([steamid64]),
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        get_game_icon_url(appid, steamid64),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    playerstats = results[0] if not isinstance(results[0], Exception) else {}
    schema_list = results[1] if not isinstance(results[1], Exception) else []
    game_info = results[2] if not isinstance(results[2], Exception) else {}
    players_res = results[3] if not isinstance(results[3], Exception) else []
    miniprofile_data = results[4] if not isinstance(results[4], Exception) else {}
    items_data = results[5] if not isinstance(results[5], Exception) else {}
    game_icon_res = results[6] if not isinstance(results[6], Exception) else ""

    achievements = (
        playerstats.get("achievements") if isinstance(playerstats, dict) else None
    )
    if not achievements:
        raise SteamValidationError(
            "未获取到成就数据，可能该游戏无成就或 steam 资料未公开"
        )

    # 1. 解析游戏信息
    game_data_obj = (
        game_info.get("data", {})
        if isinstance(game_info, dict) and game_info.get("success")
        else {}
    )
    game_name = game_data_obj.get("name") or playerstats.get("gameName") or appid
    game_icon = (
        game_icon_res
        or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_sm_120.jpg"
    )
    cover_url = (
        game_data_obj.get("header_image")
        or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
    )
    game_data = {
        "name": game_name,
        "icon_url": game_icon,
        "cover_url": cover_url,
    }

    # 2. 解析用户信息
    player = players_res[0] if isinstance(players_res, list) and players_res else {}
    user_name = player.get("personaname", "未知用户")
    friend_code = steamid64_to_friend_code(steamid64)

    avatar_url = player.get("avatarfull", "")
    if isinstance(miniprofile_data, dict) and miniprofile_data.get("avatar_url"):
        avatar_url = miniprofile_data["avatar_url"]

    avatar_frame_url = None
    if isinstance(items_data, dict):
        frame = items_data.get("avatar_frame", {})
        if frame.get("image_small"):
            avatar_frame_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{frame['image_small']}"
    if not avatar_frame_url and isinstance(miniprofile_data, dict):
        avatar_frame_url = miniprofile_data.get("avatar_frame")

    bg_url = None
    if isinstance(items_data, dict):
        mini_bg = items_data.get("mini_profile_background", {})
        if mini_bg.get("image_large"):
            bg_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{mini_bg['image_large']}"
    if not bg_url and isinstance(miniprofile_data, dict):
        bg = miniprofile_data.get("profile_background", {})
        bg_url = bg.get("image")

    user_data = {
        "name": user_name,
        "friend_code": friend_code,
        "avatar_url": avatar_url,
        "avatar_frame_url": avatar_frame_url,
        "bg_url": bg_url,
    }

    # 3. 解析成就列表并排序
    schema_map = (
        {s.get("name"): s for s in schema_list}
        if isinstance(schema_list, list)
        else {}
    )

    unlocked_list: list[dict] = []
    locked_list: list[dict] = []

    tz_cn = timezone(timedelta(hours=8))

    for ach in achievements:
        apiname = ach.get("apiname", "")
        achieved = ach.get("achieved") == 1
        unlocktime = ach.get("unlocktime", 0)
        s = schema_map.get(apiname, {})

        icon_url = (
            s.get("icon", "")
            if achieved
            else (s.get("icongray", "") or s.get("icon", ""))
        )
        name = ach.get("name") or s.get("displayName", "") or apiname
        desc = ach.get("description") or s.get("description", "") or ""

        if achieved:
            if unlocktime and unlocktime > 0:
                dt = datetime.fromtimestamp(unlocktime, tz=tz_cn)
                unlock_time_str = f"解锁时间: {dt.year}年{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
            else:
                unlock_time_str = ""
            unlocked_list.append({
                "name": name,
                "description": desc,
                "icon": icon_url,
                "achieved": True,
                "unlocktime": unlocktime,
                "unlock_time_str": unlock_time_str,
            })
        else:
            locked_list.append({
                "name": name,
                "description": desc,
                "icon": icon_url,
                "achieved": False,
                "unlocktime": 0,
                "unlock_time_str": "",
            })

    if not unlocked_list and not locked_list:
        raise SteamValidationError("该游戏暂无成就数据")

    # 规则：已解锁按解锁时间倒序排列，然后接未解锁成就
    unlocked_list.sort(key=lambda x: x.get("unlocktime", 0), reverse=True)
    all_achievements = unlocked_list + locked_list

    return game_data, user_data, all_achievements


@SV.on_command("游戏成就")
async def game_archivements(bot: Bot, ev: Event):
    appid = ""
    try:
        appid = await resolve_target_appid(bot, ev.text.strip())
        steamid64 = await resolve_target_steamid64(ev)
        if not steamid64:
            raise SteamValidationError("请先绑定 steam 账号")

        game_data, user_data, all_achievements = await build_achievement_data(
            appid, steamid64
        )
        img_bytes = await render_steam_achievement(
            game_data, user_data, all_achievements
        )
        await bot.send(MessageSegment.image(img_bytes))

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[steamUID - 游戏成就] 未知错误 appid={appid}: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")

