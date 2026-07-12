import json

from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from PIL import Image
from gsuid_core.utils.message import Message

from ..utils.api import (
    get_user_Summaries,
    get_game_info,
    get_archivement_info,
    get_archivement_img,
    get_price_data,
)
from ..utils.database.models import (
    SteamIDInfo,
    SteamBind,
    SteamArchivementInfo,
    SteamPriceInfo,
)
from ..utils.PIL.draw import draw_game_status_photo, draw_archivements_photo
from ..utils.steam_status import (
    PUSH_EVENTS,
    get_enabled_push_events,
    is_push_event_enabled,
)


async def detect_status_changes(resp) -> tuple[list, list]:
    """对比新旧状态，返回需要推送的列表和需要更新的列表"""
    push_list = []
    update_list = []
    for info in resp:
        steamid64 = info.get("steamid")
        if not steamid64:
            continue

        old_info = json.loads(await SteamIDInfo.get_steamuserinfo(steamid64) or "{}")

        if info != old_info:
            update_list.append((steamid64, info))
            # 只有 gameid 变化才需要推送
            if info.get("gameid", "") != old_info.get("gameid", ""):
                push_list.append((info, old_info))
    return push_list, update_list


async def prefetch_game_info(push_list) -> dict[str, dict]:
    """批量拉取推送列表中涉及的游戏元数据"""
    appids = set()
    for info, old_info in push_list:
        if info.get("gameid", ""):
            appids.add(info.get("gameid"))
        if old_info.get("gameid", ""):
            appids.add(old_info.get("gameid"))
    game_info_map: dict[str, dict] = {}
    for aid in appids:
        try:
            info = await get_game_info(aid)
        except Exception as error:
            logger.warning(f"[SteamPoll] 拉取游戏信息失败 appid={aid}: {error!r}")
            continue
        if info and info.get("success"):
            game_info_map[aid] = info.get("data", {})
    return game_info_map


async def process_game_status_push(push_list, game_info_map) -> None:
    """处理游戏状态变化推送，渲染图片并发送给订阅用户"""
    enabled_events = get_enabled_push_events()
    for info, old_info in push_list:
        steamid64 = info.get("steamid")
        subs = await SteamBind.get_bind_by_steamid(steamid64)
        if not subs:
            continue

        is_playing = bool(info.get("gameid", ""))
        appid = info.get("gameid") if is_playing else old_info.get("gameid", "")
        game_data = game_info_map.get(appid, {})
        game_avatar = game_data.get("header_image")

        # 提前判断是否有用户需要推送，避免无效渲染
        target_event = PUSH_EVENTS["push_start_game"] if is_playing else PUSH_EVENTS["push_end_game"]
        if target_event not in enabled_events:
            continue
        push_column = "push_start_game" if is_playing else "push_end_game"
        if not any(getattr(sub, push_column) for sub in subs):
            continue

        send_msg = await _render_game_status_message(
            is_playing, appid, info, old_info, game_avatar, game_data
        )
        await _dispatch_to_subs(subs, send_msg, push_column, steamid64)


async def update_achievement_baselines(push_list) -> None:
    """根据 gameid 变化更新成就基线，开始玩时初始化数据，结束玩时删除基线。"""
    enabled_events = get_enabled_push_events()
    if PUSH_EVENTS["push_archivement"] not in enabled_events:
        return
    for info, old_info in push_list:
        steamid64 = info.get("steamid")
        if not steamid64:
            continue
        subs = await SteamBind.get_bind_by_steamid(steamid64)
        if not subs or not any(sub.push_archivement for sub in subs):
            continue
        is_playing = bool(info.get("gameid", ""))
        appid = info.get("gameid") if is_playing else old_info.get("gameid", "")
        await _update_achievement_tracking(is_playing, appid, steamid64, enabled_events)


async def _render_game_status_message(is_playing, appid, info, old_info, game_avatar, game_data):
    """渲染游戏状态推送图片或生成文本消息"""
    game_name = game_data.get("name") or (info.get("gameextrainfo") if is_playing else old_info.get("gameextrainfo"))
    if is_playing:
        text_msg = f"{info.get('personaname')} 正在玩 {game_name}"
    else:
        text_msg = f"{info.get('personaname')} 结束游戏 {game_name}"

    try:
        IMG = await draw_game_status_photo(
            appid=appid,
            game_name=game_name,
            avatar_url=info.get("avatarfull"),
            avatar_hash=info.get("avatarhash"),
            username=info.get("personaname"),
            game_background=game_avatar,
            is_playing=is_playing,
        )
    except Exception as error:
        logger.warning(f"[SteamPoll] 绘图失败 appid={appid}: {error!r}")
        return text_msg

    if isinstance(IMG, Image.Image):
        return MessageSegment.image(IMG)
    return text_msg


async def _update_achievement_tracking(
    is_playing, appid, steamid64, enabled_events
) -> None:
    """更新单个用户的成就追踪数据"""
    if PUSH_EVENTS["push_archivement"] not in enabled_events:
        return

    if is_playing:
        try:
            resp = await get_archivement_info(appid, steamid64)
            await SteamArchivementInfo.upsert_archivement_data(
                steamid64,
                appid,
                json.dumps(resp, ensure_ascii=False),
            )
        except Exception as error:
            logger.warning(
                f"[SteamPoll] 拉取成就初始数据失败 appid={appid} steamid={steamid64}: {error!r}"
            )
    else:
        await SteamArchivementInfo.delete_archivement_data(steamid64)


async def _dispatch_to_subs(subs, send_msg, push_column, steamid64) -> None:
    """将推送消息发送给开启了相应推送开关的订阅用户"""
    for sub in subs:
        if not getattr(sub, push_column):
            continue
        try:
            await sub.send(send_msg)
        except Exception as error:
            logger.warning(f"[SteamPoll] 推送 steamid={steamid64} 失败: {error!r}")


async def flush_status_updates(update_list) -> None:
    """将有变化的状态数据写回数据库"""
    for steamid64, info in update_list:
        await SteamIDInfo.upsert_steamuserinfo(
            steamid64, json.dumps(info, ensure_ascii=False)
        )


async def poll_and_push_game_status() -> None:
    """游戏状态轮询主入口：拉取状态、检测变化、推送、更新基线、落盘。"""
    try:
        steamid_all = await SteamIDInfo.get_all_steamid64()
        if not steamid_all:
            return

        try:
            resp = await get_user_Summaries(steamid_all)
        except Exception as error:
            logger.warning(f"[SteamPoll] 拉取玩家摘要失败: {error!r}")
            return
        
        push_list, update_list = await detect_status_changes(resp)
        game_info_map = await prefetch_game_info(push_list)
        await process_game_status_push(push_list, game_info_map)
        await update_achievement_baselines(push_list)
        await flush_status_updates(update_list)
    except Exception as error:
        logger.warning(f"[SteamPoll] 游戏状态轮询失败: {error!r}")


async def poll_and_push_achievements() -> None:
    """成就轮询主入口：检测新解锁成就并推送给订阅用户。"""
    try:
        if not is_push_event_enabled(PUSH_EVENTS["push_archivement"]):
            return

        steamid_all = await SteamArchivementInfo.get_all_archivement_info()

        # 自动初始化缺少基线的成就推送用户
        tracked_steamids = {s.steamid64 for s in steamid_all}
        all_binds = await SteamBind.get_all_archivement_push_binds()
        for bind in all_binds:
            if bind.steamid64 in tracked_steamids:
                continue
            try:
                user_info = json.loads(
                    await SteamIDInfo.get_steamuserinfo(bind.steamid64) or "{}"
                )
                gameid = user_info.get("gameid", "")
                if not gameid:
                    continue
                resp = await get_archivement_info(gameid, bind.steamid64)

                if not resp.get("success", False):
                    raise Exception(f"拉取成就信息失败 {resp.get('error', '')}")
                
                await SteamArchivementInfo.upsert_archivement_data(
                    bind.steamid64,
                    gameid,
                    json.dumps(resp, ensure_ascii=False),
                )
                logger.info(
                    f"[SteamPoll] 自动初始化成就基线 appid={gameid} "
                    f"steamid={bind.steamid64}"
                )
            except Exception as error:
                logger.warning(
                    f"[SteamPoll] 自动初始化成就基线失败 "
                    f"steamid={bind.steamid64}: {error!r}"
                )

        steamid_all = await SteamArchivementInfo.get_all_archivement_info()
        if not steamid_all:
            return

        for steamid in steamid_all:
            appid = steamid.appid
            steamid64 = steamid.steamid64

            try:
                resp = await get_archivement_info(appid, steamid64)
                if not resp.get("success", False):
                    await SteamArchivementInfo.delete_archivement_data(steamid64) # 删除记录防止下次轮询
                    raise Exception(f"拉取成就信息失败 {resp.get('error', '')}")
                
            except Exception as error:
                logger.warning(
                    f"[SteamPoll] 拉取成就信息失败 appid={appid} steamid64={steamid64}:  {error!r}"
                )
                continue

            old_archivement_info = json.loads(steamid.archivement_data or "{}")
            new_archivement_info = resp

            old_achievements = {
                a['apiname']: a
                for a in old_archivement_info.get('achievements', [])
            }
            newly_achieved = [
                a for a in new_archivement_info.get('achievements', [])
                if a.get('achieved') == 1
                and old_achievements.get(a['apiname'], {}).get('achieved') == 0
            ]

            if not newly_achieved:
                continue

            subs = await SteamBind.get_bind_by_steamid(steamid64)
            game_name = new_archivement_info.get('gameName', '未知游戏')

            gamer_info = json.loads(await SteamIDInfo.get_steamuserinfo(steamid64) or "{}")
            gamer_name = gamer_info.get("personaname", steamid64)
            gamer_img_url = gamer_info.get("avatarfull", "")

            for ach in newly_achieved:
                archivement_name = ach.get("name", "无名称")
                archivement_desc = ach.get("description", "无描述")
                text_msg = (
                    f"{gamer_name} 解锁成就：\n"
                    f"游戏：{game_name}\n"
                    f"成就：{archivement_name}\n"
                    f"描述：{archivement_desc}"
                )

                send_msg = None
                try:
                    archivement_img_url = await get_archivement_img(
                        appid, ach.get("apiname", "")
                    )
                    IMG = await draw_archivements_photo(
                        gamer_name=gamer_name,
                        gamer_img_url=gamer_img_url,
                        archivement_name=archivement_name,
                        archivement_img_url=archivement_img_url,
                        game_name=game_name,
                        archivement_desc=archivement_desc,
                    )
                    if isinstance(IMG, Image.Image):
                        send_msg = MessageSegment.image(IMG)
                except Exception as error:
                    logger.warning(
                        f"[SteamPoll] 成就图片渲染失败 appid={appid} steamid={steamid64}: {error!r}"
                    )

                if send_msg is None:
                    send_msg = text_msg

                for sub in subs:
                    if not sub.push_archivement:
                        continue
                    try:
                        await sub.send(send_msg)
                    except Exception as error:
                        logger.warning(
                            f"[SteamPoll] 推送成就失败 steamid={steamid64}: {error!r}"
                        )

            await SteamArchivementInfo.upsert_archivement_data(
                steamid64,
                appid,
                json.dumps(new_archivement_info, ensure_ascii=False),
            )
    except Exception as error:
        logger.warning(f"[SteamPoll] 成就轮询失败: {error!r}")


#-----------------------------------------------------
# 游戏降价轮询
#-----------------------------------------------------

async def detect_price_drops(new_prices: dict) -> tuple[list, list]:
    """对比新旧价格，返回降价列表和需要更新的列表"""
    drops = []
    update_list = []
    all_subs = await SteamPriceInfo.get_all_price_subs()
    old_map = {sub.appid: sub.price_data for sub in all_subs}

    for appid, new_entry in new_prices.items():
        if not new_entry.get("success"):
            continue
        new_overview = new_entry.get("data", {}).get("price_overview")
        if not new_overview:
            continue

        old_overview = json.loads(old_map.get(appid) or "{}")
        old_final = old_overview.get("final")
        new_final = new_overview.get("final")

        if (
            old_final is not None
            and new_final is not None
            and new_final < old_final
        ):
            drops.append((appid, old_overview, new_overview))

        update_list.append((appid, new_overview))

    return drops, update_list


async def process_game_sale_push(drops: list) -> None:
    """处理游戏降价推送，发送消息给订阅用户"""
    if not drops:
        return

    all_subs = await gs_subscribe.get_subscribe(task_name="steam商店降价订阅")
    if not all_subs:
        return

    subs_by_appid: dict[str, list] = {}
    for sub in all_subs:
        if sub.uid:
            subs_by_appid.setdefault(sub.uid, []).append(sub)

    for appid, old_overview, new_overview in drops:
        subs = subs_by_appid.get(appid)
        if not subs:
            continue
        send_msg = _render_sale_message(appid, old_overview, new_overview)
        for sub in subs:
            try:
                await sub.send([MessageSegment.at(sub.user_id), send_msg])
            except Exception as error:
                logger.warning(
                    f"[SteamPoll] 推送降价失败 appid={appid}: {error!r}"
                )


def _render_sale_message(appid, old_overview, new_overview) -> Message:
    """生成降价推送文本消息"""
    text = MessageSegment.text(f"游戏 {appid} 降价！\n"
           f"旧价：{old_overview.get('final_formatted', 'N/A')}\n"
           f"现价：{new_overview.get('final_formatted', 'N/A')}\n"
           f"折扣：{new_overview.get('discount_percent', 'N/A')}%\n"
           f"点击查看: https://store.steampowered.com/app/{appid}")
    return text



async def flush_price_updates(update_list: list) -> None:
    """将最新价格数据写回数据库"""
    for appid, new_overview in update_list:
        await SteamPriceInfo.update_price_data(
            appid, json.dumps(new_overview, ensure_ascii=False)
        )


async def poll_and_push_game_sale() -> None:
    """游戏降价轮询主入口：拉取价格、检测降价、推送、落盘。"""
    try:
        appids = await SteamPriceInfo.get_all_appids()
        if not appids:
            return

        try:
            new_prices = await get_price_data(appids)
        except Exception as error:
            logger.warning(f"[SteamPoll] 拉取价格数据失败: {error!r}")
            return

        drops, update_list = await detect_price_drops(new_prices)
        await process_game_sale_push(drops)
        await flush_price_updates(update_list)
    except Exception as error:
        logger.warning(f"[SteamPoll] 游戏降价轮询失败: {error!r}")
