from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.utils.database.models import CoreUser

from ..utils.api import get_game_info
from ..utils.database.models import SteamBind, SteamPlayRecord
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.render import render_game_ranking
from ..utils.utils import time_convert_s

ranking_sv = SV("steam排名服务")


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
    if records is None:
        raise SteamError("查询游玩记录失败，请稍后重试")

    user_durations: dict[str, int] = {}
    for record in records:
        uid = steamid_to_user.get(record.steamid64)
        if uid is None:
            continue
        duration = record.end_ts - record.start_ts  # type: ignore
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


async def get_game_ranking_list(group_id: str) -> list[dict]:
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
    if records is None:
        raise SteamError("查询游玩记录失败，请稍后重试")

    app_durations: dict[str, int] = {}
    for record in records:
        duration = record.end_ts - record.start_ts  # type: ignore
        app_durations[record.appid] = app_durations.get(record.appid, 0) + duration

    sorted_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)

    ranking_list: list[dict] = []
    for appid, total_duration in sorted_apps:
        game_name = appid
        cover_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
        try:
            info = await get_game_info(appid)
            if info and info.get("success"):
                data = info.get("data", {})
                name = data.get("name", "")
                if name:
                    game_name = name
                header_img = data.get("header_image")
                if header_img:
                    cover_url = header_img
        except Exception:
            pass
        ranking_list.append({
            "appid": appid,
            "game_name": game_name,
            "total_duration": total_duration,
            "cover_url": cover_url,
        })

    return ranking_list


@ranking_sv.on_command(("群排行", "群排名"))
async def group_ranking(bot: Bot, ev: Event):
    """按用户游戏时长从高到低取5位返回"""
    try:
        if not ev.group_id:
            raise SteamValidationError("请在群聊中使用此功能")

        ranking_list = await get_group_ranking_list(ev.group_id)
        text = ev.text.strip()
        if text.isdigit() and int(text) > 0:
            top = ranking_list[:int(text)]
        else:
            top = ranking_list[:5]

        if not top:
            await bot.send("本群暂无游戏时长排行数据")
            return

        reply_text = f"本群游戏时长排行 Top{len(top)}：\n"
        for i, item in enumerate(top, 1):
            users = await CoreUser.select_rows(user_id=item["user_id"], group_id=ev.group_id)
            if users and users[0].user_name:
                name = users[0].user_name
            else:
                name = item["user_id"]

            reply_text += f"{i}. {name} ({time_convert_s(item['total_duration'])})\n"

        await bot.send(reply_text)

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamRanking - 群排行] 未知错误: {e!r}")
        await bot.send("发生未知错误，请联系管理员查看控制台")


@ranking_sv.on_command(("群游戏排行", "群游戏排名"))
async def game_ranking(bot: Bot, ev: Event):
    """按群内所有游戏的总游玩时长从高到低排序，使用 Playwright 渲染图片返回"""
    try:
        if not ev.group_id:
            raise SteamValidationError("请在群聊中使用此功能")

        ranking_list = await get_game_ranking_list(ev.group_id)
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

        img_bytes = await render_game_ranking(top)
        await bot.send(MessageSegment.image(img_bytes))

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamRanking - 群游戏排行] 未知错误: {e!r}")
        await bot.send("发生未知错误，请联系管理员查看控制台")

