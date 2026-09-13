import asyncio
from datetime import datetime, timezone, timedelta

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..utils.Api import (
    get_archivement_info,
    get_archivement_schema,
    get_game_cover_url,
    get_game_icon_url,
    get_game_info,
    get_miniprofile,
    get_official_cover_url,
    get_profile_items_equipped,
    get_user_Summaries,
)
from ..utils.exceptions import (
    SteamError,
    SteamRenderError,
    SteamValidationError,
    unwrap,
)
from ..utils.helpers.profile import resolve_profile_assets
from ..utils.render import render_steam_achievement
from ..utils.utils import resolve_target_appid, resolve_target_steamid64, steamid64_to_friend_code
from ..utils.helpers.command import steam_command

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

    for r in (results[0], results[1], results[3]):
        if isinstance(r, SteamError):
            raise r

    (
        playerstats,
        schema_list,
        game_info,
        players_res,
        miniprofile_data,
        items_data,
        game_icon_res,
    ) = (
        unwrap(r, d)
        for r, d in zip(results, ({}, [], {}, [], {}, {}, ""))
    )

    achievements = (
        playerstats.get("achievements") if isinstance(playerstats, dict) else None
    )
    if not achievements:
        raise SteamValidationError(
            "未获取到成就数据，可能该游戏无成就、steam 资料未公开或登录授权已失效"
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
        or get_official_cover_url(appid, "capsule_sm_120")
    )
    cover_url = await get_game_cover_url(appid, header_image=game_data_obj.get("header_image"))
    game_data = {
        "name": game_name,
        "icon_url": game_icon,
        "cover_url": cover_url,
    }

    # 2. 解析用户信息（头像 / 头像框 / 背景三源统一解析）
    player = players_res[0] if isinstance(players_res, list) and players_res else {}
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


@steam_command("steamUID - 游戏成就")
@SV.on_command("游戏成就")
async def game_archivements(bot: Bot, ev: Event):
    appid = ""
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


