import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.utils.database.models import CoreUser

from ..SteamConfig import SteamConfig
from ..utils.Api import (
    get_game_cover_url,
    get_game_icon_url,
    get_game_info,
    get_user_Summaries,
)
from ..utils.database.models import SteamBind, SteamPlayRecord
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.helpers.profile import resolve_profile_assets
from ..utils.helpers.command import steam_command
from ..utils.render import (
    render_game_ranking,
    render_game_user_ranking,
    render_group_member_status,
    render_user_ranking,
)
from ..utils.helpers.steam_state import resolve_player_status
from ..utils.helpers.game import resolve_target_appid
from ..utils.utils import (
    auto2steamid64,
    steamid64_to_friend_code,
    time_convert_s,
)

ranking_sv = SV("steam排名服务")


async def _fetch_game_detail(appid: str, total_duration: int) -> dict:
    game_name = appid
    header_img = None
    try:
        info = await get_game_info(appid)
        if info and info.get("success"):
            data = info.get("data", {})
            name = data.get("name", "")
            if name:
                game_name = name
            header_img = data.get("header_image")
    except Exception:
        pass
    cover_url = await get_game_cover_url(appid, header_image=header_img)
    return {
        "appid": appid,
        "game_name": game_name,
        "total_duration": total_duration,
        "cover_url": cover_url,
    }


async def get_group_ranking_list(group_id: str) -> list[dict]:
    """获取群排名列表"""
    binds = await SteamBind.get_binds_by_group(group_id)
    if not binds:
        return []

    steamid_to_user: dict[str, str] = {}
    user_steamids: dict[str, list[str]] = {}
    all_steamids: list[str] = []

    for bind in binds:
        sid = bind.steamid64
        uid = bind.user_id
        steamid_to_user[sid] = uid
        all_steamids.append(sid)
        if uid not in user_steamids:
            user_steamids[uid] = []
        if sid not in user_steamids[uid]:
            user_steamids[uid].append(sid)

    records = await SteamPlayRecord.get_records_by_steamids(all_steamids)

    user_durations: dict[str, int] = {}
    for record in records:
        uid = steamid_to_user.get(record.steamid64)
        if uid is None:
            continue
        if not record.end_ts or not record.start_ts:
            continue
        duration = record.end_ts - record.start_ts  # type: ignore
        if duration <= 0:
            continue
        user_durations[uid] = user_durations.get(uid, 0) + duration

    ranking_list = [
        {
            "user_id": uid,
            "total_duration": duration,
            "steamid64s": user_steamids.get(uid, []),
        }
        for uid, duration in user_durations.items()
    ]
    ranking_list.sort(key=lambda x: x["total_duration"], reverse=True)

    return ranking_list


async def get_game_ranking_list(group_id: str, limit: int | None = None) -> list[dict]:
    """获取群内游戏排行列表（按游戏总时长降序，不区分用户）"""
    binds = await SteamBind.get_binds_by_group(group_id)
    if not binds:
        return []

    all_steamids: list[str] = []
    seen: set[str] = set()
    for bind in binds:
        sid = bind.steamid64
        if sid not in seen:
            seen.add(sid)
            all_steamids.append(sid)

    records = await SteamPlayRecord.get_records_by_steamids(all_steamids)

    app_durations: dict[str, int] = {}
    for record in records:
        if not record.end_ts or not record.start_ts:
            continue
        duration = record.end_ts - record.start_ts  # type: ignore
        if duration <= 0:
            continue
        app_durations[record.appid] = app_durations.get(record.appid, 0) + duration

    sorted_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)
    if limit is not None and limit > 0:
        sorted_apps = sorted_apps[:limit]

    ranking_list = await asyncio.gather(
        *(_fetch_game_detail(appid, total_duration) for appid, total_duration in sorted_apps)
    )

    return list(ranking_list)


async def get_user_game_ranking_list(
    steamid64s: list[str],
    limit: int | None = None,
) -> list[dict]:
    """获取指定用户/Steam账号列表在群内的游戏排行列表（按游戏总时长降序）"""
    if not steamid64s:
        return []

    records = await SteamPlayRecord.get_records_by_steamids(steamid64s)

    app_durations: dict[str, int] = {}
    for record in records:
        if not record.end_ts or not record.start_ts:
            continue
        duration = record.end_ts - record.start_ts  # type: ignore
        if duration <= 0:
            continue
        app_durations[record.appid] = app_durations.get(record.appid, 0) + duration

    sorted_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)
    if limit is not None and limit > 0:
        sorted_apps = sorted_apps[:limit]

    ranking_list = await asyncio.gather(
        *(_fetch_game_detail(appid, total_duration) for appid, total_duration in sorted_apps)
    )

    return list(ranking_list)


async def get_game_user_ranking_list(
    group_id: str,
    appid: str,
) -> tuple[list[dict], list[str]]:
    """获取指定游戏在群内的玩家排行列表（按游玩总时长降序）"""
    binds = await SteamBind.get_binds_by_group(group_id)
    if not binds:
        return [], []

    steamid_to_user: dict[str, str] = {}
    user_steamids: dict[str, list[str]] = {}
    all_steamids: list[str] = []

    for bind in binds:
        sid = bind.steamid64
        uid = bind.user_id
        steamid_to_user[sid] = uid
        all_steamids.append(sid)
        if uid not in user_steamids:
            user_steamids[uid] = []
        if sid not in user_steamids[uid]:
            user_steamids[uid].append(sid)

    records = await SteamPlayRecord.get_records_by_steamids(all_steamids)

    user_durations: dict[str, int] = {}
    played_steamids: list[str] = []
    for record in records:
        if str(record.appid) != str(appid):
            continue
        uid = steamid_to_user.get(record.steamid64)
        if uid is None:
            continue
        if not record.end_ts or not record.start_ts:
            continue
        duration = record.end_ts - record.start_ts  # type: ignore
        if duration <= 0:
            continue
        user_durations[uid] = user_durations.get(uid, 0) + duration
        if record.steamid64 not in played_steamids:
            played_steamids.append(record.steamid64)

    ranking_list = [
        {
            "user_id": uid,
            "total_duration": duration,
            "steamid64s": user_steamids.get(uid, []),
        }
        for uid, duration in user_durations.items()
    ]
    ranking_list.sort(key=lambda x: x["total_duration"], reverse=True)

    return ranking_list, played_steamids



@steam_command("SteamRanking - 群排行")
@ranking_sv.on_command(("群玩家排行", "群玩家排名", "群玩家统计"))
async def group_ranking(bot: Bot, ev: Event):
    """按用户游戏时长从高到低排序，使用 Playwright 渲染图片返回"""
    if not ev.group_id:
        raise SteamValidationError("请在群聊中使用此功能")

    ranking_list = await get_group_ranking_list(ev.group_id)
    if not ranking_list:
        await bot.send("本群暂无游戏时长排行数据")
        return

    text = ev.text.strip()
    if text.isdigit() and int(text) > 0:
        top = ranking_list[:int(text)]
    else:
        top = ranking_list[:10]

    if not top:
        await bot.send("本群暂无游戏时长排行数据")
        return

    display_list = []
    for item in top:
        uid = str(item["user_id"])
        users = await CoreUser.select_rows(user_id=uid, group_id=ev.group_id)
        user_name = uid
        avatar_url = None
        if users and users[0]:
            if users[0].user_name and users[0].user_name != "1":
                user_name = str(users[0].user_name)
            if users[0].user_icon and users[0].user_icon != "1":
                avatar_url = str(users[0].user_icon)

        display_list.append({
            "user_id": uid,
            "user_name": user_name,
            "total_duration": item["total_duration"],
            "avatar_url": avatar_url,
        })

    img_bytes = await render_user_ranking(display_list)
    await bot.send(MessageSegment.image(img_bytes))



@steam_command("SteamRanking - 群游戏排行")
@ranking_sv.on_command(("群游戏排行", "群游戏排名", "群游戏统计"))
async def game_ranking(bot: Bot, ev: Event):
    """按群内所有游戏的总游玩时长从高到低排序，使用 Playwright 渲染图片返回"""
    if not ev.group_id:
        raise SteamValidationError("请在群聊中使用此功能")

    text = ev.text.strip()
    limit = int(text) if text.isdigit() and int(text) > 0 else 10

    ranking_list = await get_game_ranking_list(ev.group_id, limit=limit)
    if not ranking_list:
        await bot.send("本群暂无游戏时长排行数据")
        return

    img_bytes = await render_game_ranking(ranking_list)
    await bot.send(MessageSegment.image(img_bytes))



async def _build_ranking_account_pill(steamid64: str) -> dict:
    """为排行卡片右上角账号胶囊组装 Steam 用户资料"""
    players_res = await get_user_Summaries([steamid64])
    player = players_res[0] if isinstance(players_res, list) and players_res else {}
    assets = await resolve_profile_assets(steamid64, player=player)
    return {
        "name": player.get("personaname", "未知用户"),
        "friend_code": steamid64_to_friend_code(steamid64),
        "avatar_url": assets.avatar_url,
        "avatar_frame_url": assets.avatar_frame_url,
        "bg_url": assets.bg_url,
    }


@steam_command("SteamRanking - 我的统计")
@ranking_sv.on_command(("统计", "排行", "排名"))
async def my_game_ranking(bot: Bot, ev: Event):
    """按用户个人在群内的游戏总时长从高到低排序，使用 Playwright 渲染图片返回"""
    if not ev.group_id:
        raise SteamValidationError("请在群聊中使用此功能")

    limit = 10
    target_user_id = ev.user_id
    target_steamid64 = None

    if ev.at:
        if not SteamConfig.get_config("AllowAt").data:
            raise SteamValidationError("未开启 @ 他人获取他人信息功能")
        target_user_id = ev.at
        # @他人时仅剩一个可选参数：条数
        words = ev.text.strip().split()
        if words and words[0].isdigit():
            limit = int(words[0])
    else:
        # 参数按空格分割：第 1 个为好友码/steamid64，第 2 个为条数
        words = ev.text.strip().split()
        if words:
            sid = auto2steamid64(words[0])
            if sid:
                target_steamid64 = sid
            if len(words) >= 2 and words[1].isdigit():
                limit = int(words[1])

    if target_steamid64:
        target_steamids = [target_steamid64]
        is_self = False
        pill_steamid = target_steamid64
    else:
        is_self = (target_user_id == ev.user_id)
        binds = await SteamBind.get_binds_by_user(
            ev.bot_id, target_user_id, ev.user_type, ev.group_id
        )
        if not binds:
            raise SteamValidationError(
                "您在当前群未绑定 Steam 账号，请先绑定"
                if is_self
                else "对方在当前群未绑定 Steam 账号"
            )
        # 主绑定（列表首个）用于右上角账号胶囊展示
        target_steamids = list({b.steamid64 for b in binds})
        pill_steamid = binds[0].steamid64

    ranking_list = await get_user_game_ranking_list(target_steamids, limit=limit)
    if not ranking_list:
        await bot.send(
            "您在当前群暂无游戏时长数据"
            if is_self
            else "对方在当前群暂无游戏时长数据"
        )
        return

    title_text = "steam统计"

    # 右上角账号胶囊：展示查询目标的 Steam 资料
    user_data = None
    try:
        user_data = await _build_ranking_account_pill(pill_steamid)
    except Exception as e:
        logger.warning(f"[SteamUID - 统计] 获取账号胶囊资料失败，跳过胶囊: {e}")

    img_bytes = await render_game_ranking(
        ranking_list, title_text=title_text, user_data=user_data
    )
    await bot.send(MessageSegment.image(img_bytes))



@steam_command("SteamRanking - 群游戏玩家排行")
@ranking_sv.on_command(("群游戏玩家排行", "群游戏玩家排名", "群游戏玩家统计"))
async def game_user_ranking(bot: Bot, ev: Event):
    """按指定游戏在群内的用户游玩时长从高到低排序，使用 Playwright 渲染图片返回"""
    if not ev.group_id:
        raise SteamValidationError("请在群聊中使用此功能")

    text = ev.text.strip()
    appid, limit = await resolve_target_appid(bot, text, parse_limit=True)

    ranking_list, played_steamids = await get_game_user_ranking_list(ev.group_id, appid)
    if not ranking_list:
        await bot.send(f"未找到 {appid} 的相关游玩数据！")
        return

    top = ranking_list[:limit]
    if not top:
        await bot.send(f"未找到 {appid} 的相关游玩数据！")
        return

    # 获取游戏名称
    game_name = appid
    try:
        info = await get_game_info(appid)
        if info and info.get("success"):
            name = info.get("data", {}).get("name", "")
            if name:
                game_name = name
    except Exception:
        pass

    # 获取游戏小图标 (优先使用玩过该游戏的玩家steamid获取客户端小图标)
    sample_sid = played_steamids[0] if played_steamids else None
    game_logo_url = await get_game_icon_url(appid, sample_sid)

    display_list = []
    for item in top:
        uid = str(item["user_id"])
        users = await CoreUser.select_rows(user_id=uid, group_id=ev.group_id)
        user_name = uid
        avatar_url = None
        if users and users[0]:
            if users[0].user_name and users[0].user_name != "1":
                user_name = str(users[0].user_name)
            if users[0].user_icon and users[0].user_icon != "1":
                avatar_url = str(users[0].user_icon)

        display_list.append({
            "user_id": uid,
            "user_name": user_name,
            "total_duration": item["total_duration"],
            "avatar_url": avatar_url,
        })

    title_text = f"steam群游戏玩家排行 Top{len(display_list)}: "
    img_bytes = await render_game_user_ranking(
        ranking_data=display_list,
        appid=appid,
        game_name=game_name,
        game_logo_url=game_logo_url,
        top_count=len(display_list),
        title_text=title_text,
    )
    await bot.send(MessageSegment.image(img_bytes))



async def _fetch_member_online_bg(steamid64: str) -> str | None:
    """获取在线用户的迷你资料背景 URL（统一走 resolve_profile_assets 三源解析）"""
    assets = await resolve_profile_assets(steamid64)
    return assets.bg_url


async def _enrich_member_item(candidate: dict, group_id: str) -> dict:
    """为选中的活跃群友补充 QQ 资料、游戏信息与背景图"""
    uid = candidate["user_id"]
    status = candidate["status"]
    steamid64 = candidate["steamid64"]
    game_id = candidate["game_id"]
    game_name = candidate["game_name"]

    user_name = uid
    avatar_url = None
    try:
        users = await CoreUser.select_rows(user_id=uid, group_id=group_id)
        if users and users[0]:
            if users[0].user_name and users[0].user_name != "1":
                user_name = str(users[0].user_name)
            if users[0].user_icon and users[0].user_icon != "1":
                avatar_url = str(users[0].user_icon)
    except Exception:
        pass

    bg_url = None
    if status == "ingame":
        if not game_name and game_id:
            try:
                info = await get_game_info(game_id)
                if info and info.get("success"):
                    name = info.get("data", {}).get("name", "")
                    if name:
                        game_name = name
            except Exception:
                pass
        status_text = f"游戏中：{game_name or '未知游戏'}"
        if game_id:
            bg_url = await get_game_cover_url(game_id)
    else:
        status_text = "在线"
        bg_url = await _fetch_member_online_bg(steamid64)

    return {
        "user_id": uid,
        "user_name": user_name,
        "avatar_url": avatar_url,
        "status": status,
        "status_text": status_text,
        "bg_url": bg_url,
    }


async def get_group_member_status_list(group_id: str) -> tuple[list[dict], bool]:
    """获取本群活跃（游戏中 / 在线）群友状态列表，最多返回 10 人，返回 (display_list, has_more)"""
    binds = await SteamBind.get_binds_by_group(group_id)
    if not binds:
        return [], False

    user_binds: dict[str, list[SteamBind]] = {}
    all_steamids_set: set[str] = set()
    for b in binds:
        uid = b.user_id
        if uid not in user_binds:
            user_binds[uid] = []
        user_binds[uid].append(b)
        all_steamids_set.add(b.steamid64)

    if not all_steamids_set:
        return [], False

    all_steamids = list(all_steamids_set)
    summaries = await get_user_Summaries(all_steamids)
    summary_map: dict[str, dict] = {
        p.get("steamid", ""): p for p in summaries if isinstance(p, dict) and p.get("steamid")
    }

    active_user_candidates = []
    for uid, u_binds in user_binds.items():
        ingames = []
        onlines = []
        for b in u_binds:
            p = summary_map.get(b.steamid64, {})
            status, game_name = resolve_player_status(p)
            if status == "ingame":
                ingames.append({
                    "bind": b,
                    "status": "ingame",
                    "game_id": str(p.get("gameid", "")),
                    "game_name": game_name or p.get("gameextrainfo", ""),
                })
            elif status == "online":
                onlines.append({
                    "bind": b,
                    "status": "online",
                    "game_id": None,
                    "game_name": None,
                })

        chosen = None
        if ingames:
            chosen = next((item for item in ingames if item["bind"].is_main_id), None)
        elif onlines:
            chosen = next((item for item in onlines if item["bind"].is_main_id), None)

        if (ingames or onlines) and chosen is None:
            # 正常绑定数据必有主 ID；缺失说明数据被改动或存在 bug，直接报错
            raise SteamError(
                f"用户 {uid} 的绑定数据缺失主账号标记，请先使用【steam切换】设置主账号"
            )

        if chosen:
            active_user_candidates.append({
                "user_id": uid,
                "status": chosen["status"],
                "steamid64": chosen["bind"].steamid64,
                "game_id": chosen["game_id"],
                "game_name": chosen["game_name"],
            })

    if not active_user_candidates:
        return [], False

    # 排序：游戏中置顶，在线次之
    active_user_candidates.sort(key=lambda x: 0 if x["status"] == "ingame" else 1)

    has_more = len(active_user_candidates) > 10
    top_candidates = active_user_candidates[:10]

    display_list = await asyncio.gather(
        *(_enrich_member_item(c, group_id) for c in top_candidates)
    )

    return list(display_list), has_more


@steam_command("SteamRanking - 群友状态")
@ranking_sv.on_command("群友状态")
async def group_member_status(bot: Bot, ev: Event):
    """查看当前群已绑定 Steam 用户的实时状态（游戏中/在线），使用 Playwright 渲染图片返回"""
    if not ev.group_id:
        raise SteamValidationError("请在群聊中使用此功能")

    display_list, has_more = await get_group_member_status_list(ev.group_id)
    if not display_list:
        await bot.send("本群当前暂无在线或正在玩游戏的群友")
        return

    img_bytes = await render_group_member_status(
        member_data_list=display_list,
        has_more=has_more,
        title_text="steam群友状态",
    )
    await bot.send(MessageSegment.image(img_bytes))




