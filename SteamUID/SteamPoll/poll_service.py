import asyncio
import json
import time
from collections import defaultdict

from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.message import Message

from ..utils.api import (
    get_user_Summaries,
    get_game_info,
    get_archivement_info,
    get_archivement_img,
    get_price_data,
    get_game_announcements,
)
from ..utils.database.models import (
    SteamIDInfo,
    SteamBind,
    SteamArchivementInfo,
    SteamPriceInfo,
    SteamAnnounceInfo,
    SteamPlayRecord,
)
from ..utils.render import (
    render_game_status,
    render_achievement_push,
    render_game_announce,
    render_game_price_drop,
)
from ..SteamConfig.interface import SteamAPI
from ..utils.utils import (
    PUSH_EVENTS,
    get_enabled_push_events,
    is_push_event_enabled,
    get_user_group_nickname,
    steamid64_to_friend_code,
    get_user_static_avatar_frame,
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


async def prefetch_avatar_frames(push_list) -> dict[str, str | None]:
    """批量拉取推送列表中涉及用户的静态头像框"""
    steamids = {
        info.get("steamid") for info, _ in push_list if info.get("steamid")
    }
    if not steamids:
        return {}
    tasks = {sid: get_user_static_avatar_frame(sid) for sid in steamids}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    frame_map = {}
    for sid, res in zip(tasks.keys(), results):
        frame_map[sid] = res if isinstance(res, str) else None
    return frame_map


async def process_game_status_push(
    push_list,
    game_info_map,
    avatar_frame_map: dict[str, str | None] | None = None,
) -> None:
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
        avatar_frame_url = (
            avatar_frame_map.get(steamid64) if avatar_frame_map else None
        )

        # 提前判断是否有用户需要推送，避免无效渲染
        target_event = PUSH_EVENTS["push_start_game"] if is_playing else PUSH_EVENTS["push_end_game"]
        if target_event not in enabled_events:
            continue
        push_column = "push_start_game" if is_playing else "push_end_game"

        push_subs_by_group: dict[str | None, list] = defaultdict(list)
        for sub in subs:
            if getattr(sub, push_column):
                push_subs_by_group[sub.group_id].append(sub)

        if not any(push_subs_by_group.values()):
            continue

        # 预取各群用户群昵称
        group_name_cache: dict[str | None, str | None] = {}
        for gid in push_subs_by_group:
            gsubs = push_subs_by_group[gid]
            group_name_cache[gid] = await get_user_group_nickname(
                gsubs[0].bot_id, gsubs[0].user_id, gid
            )

        rendered_cache: dict[str | None, Any] = {}
        for group_id, group_subs in push_subs_by_group.items():
            group_name = group_name_cache[group_id]
            if group_name not in rendered_cache:
                rendered_cache[group_name] = await _render_game_status_message(
                    is_playing,
                    appid,
                    info,
                    old_info,
                    game_avatar,
                    game_data,
                    group_name=group_name,
                    avatar_frame_url=avatar_frame_url,
                )
            send_msg = rendered_cache[group_name]

            for sub in group_subs:
                try:
                    await sub.send(send_msg)
                except Exception as error:
                    logger.warning(f"[SteamPoll] 推送 steamid={steamid64} 失败: {error!r}")


async def update_achievement_baselines(push_list) -> None:
    """根据 gameid 变化更新成就基线，开始玩时初始化数据，结束玩时删除基线。"""
    enabled_events = get_enabled_push_events()
    if PUSH_EVENTS["push_archivement"] not in enabled_events:
        return
    for info, old_info in push_list:
        steamid64 = info.get("steamid")
        if not steamid64:
            continue
        is_playing = bool(info.get("gameid", ""))
        appid = info.get("gameid") if is_playing else old_info.get("gameid", "")
        if not is_playing:
            await SteamArchivementInfo.delete_archivement_data(steamid64)
            continue
        subs = await SteamBind.get_bind_by_steamid(steamid64)
        if not subs or not any(sub.push_archivement for sub in subs):
            continue
        await _update_achievement_tracking(is_playing, appid, steamid64, enabled_events)


async def _render_game_status_message(
    is_playing,
    appid,
    info,
    old_info,
    game_avatar,
    game_data,
    group_name: str | None = None,
    avatar_frame_url: str | None = None,
):
    """渲染游戏状态推送图片或生成文本消息"""
    username = info.get("personaname") or ""
    game_name = (
        game_data.get("name")
        or (info.get("gameextrainfo") if is_playing else old_info.get("gameextrainfo"))
        or "未知游戏"
    )
    avatar_url = info.get("avatarfull") or ""
    avatar_hash = info.get("avatarhash") or ""

    user_display = f"{username} ({group_name})" if group_name else username
    if is_playing:
        text_msg = f"{user_display} 正在玩 {game_name}"
    else:
        text_msg = f"{user_display} 结束游戏 {game_name}"

    # 优先尝试 Playwright 渲染，失败时降级为文本消息
    try:
        img_bytes = await render_game_status(
            username=username,
            game_name=game_name,
            avatar_url=avatar_url,
            avatar_frame_url=avatar_frame_url,
            game_background=game_avatar,
            is_playing=is_playing,
            group_name=group_name,
        )
        if img_bytes:
            return MessageSegment.image(img_bytes)
    except Exception as error:
        logger.warning(f"[SteamPoll] Playwright 渲染游戏状态失败: {error!r}")

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
    """将有变化的状态数据写回状态轮询数据库"""
    for steamid64, info in update_list:
        await SteamIDInfo.upsert_steamuserinfo(
            steamid64, json.dumps(info, ensure_ascii=False)
        )

async def update_game_record(push_list) -> None:
    """写入游戏记录数据库"""
    now = int(time.time())
    for info, old_info in push_list:
        steamid64 = info.get("steamid")
        if not steamid64:
            continue
        old_appid = old_info.get("gameid", "")
        new_appid = info.get("gameid", "")
        # 结束旧游戏（覆盖"切换游戏"与"退出游戏"两种场景）
        if old_appid:
            ret = await SteamPlayRecord.upsert_record(steamid64, old_appid, end_ts=now)
            if ret != 0:
                logger.warning(
                    f"[SteamPoll] 结束游玩记录失败: steamid={steamid64} appid={old_appid}"
                )
        # 开始新游戏
        if new_appid:
            await SteamPlayRecord.upsert_record(steamid64, new_appid, now)
            
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
        avatar_frame_map = await prefetch_avatar_frames(push_list)
        await process_game_status_push(push_list, game_info_map, avatar_frame_map)
        await update_achievement_baselines(push_list)
        await flush_status_updates(update_list)
        await update_game_record(push_list)
        
    except Exception as error:
        logger.warning(f"[SteamPoll] 游戏状态轮询失败: {error!r}")


_last_achievement_switch_enabled: bool | None = None


async def poll_and_push_achievements() -> None:
    """成就轮询主入口：检测新解锁成就并推送给订阅用户。"""
    global _last_achievement_switch_enabled
    try:
        is_enabled = is_push_event_enabled(PUSH_EVENTS["push_archivement"])
        if not is_enabled:
            # 总开关关闭时，清空成就追踪基线，防止后续开启后用旧基线对比产生刷屏
            if _last_achievement_switch_enabled is not False:
                await SteamArchivementInfo.delete_all_archivement_data()
                _last_achievement_switch_enabled = False
            return

        # 若此前总开关为关闭状态（或刚启动首次运行），清空可能残留的历史旧基线，重新拉取最新成就作为初始基线
        if _last_achievement_switch_enabled is not True:
            await SteamArchivementInfo.delete_all_archivement_data()
            _last_achievement_switch_enabled = True

        steamid_all = await SteamArchivementInfo.get_all_archivement_info()

        # 自动初始化缺少基线的成就推送用户（此时拉取的信息仅作为基线，不推送）
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

        # 仅对在此轮轮询前已有基线的用户进行增量成就检测并推送
        if not steamid_all:
            return

        for steamid in steamid_all:
            appid = steamid.appid
            steamid64 = steamid.steamid64

            # 校验用户当前是否仍在游玩对应游戏
            try:
                user_info = json.loads(
                    await SteamIDInfo.get_steamuserinfo(steamid64) or "{}"
                )
                current_gameid = user_info.get("gameid", "")
                if current_gameid != appid:
                    # 游戏已结束或已切换，删除该基线
                    await SteamArchivementInfo.delete_archivement_data(steamid64)
                    continue
            except Exception:
                pass

            # 校验是否仍有订阅者开启了该用户的成就推送
            subs = await SteamBind.get_bind_by_steamid(steamid64)
            if not subs or not any(sub.push_archivement for sub in subs):
                await SteamArchivementInfo.delete_archivement_data(steamid64)
                continue

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

            try:
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

                # 按群分组，只保留开启了成就推送的订阅者
                push_subs_by_group: dict[str | None, list] = defaultdict(list)
                for sub in subs:
                    if sub.push_archivement:
                        push_subs_by_group[sub.group_id].append(sub)

                if not any(push_subs_by_group.values()):
                    continue

                # 预取各群用户群昵称
                group_name_cache: dict[str | None, str | None] = {}
                for gid in push_subs_by_group:
                    gsubs = push_subs_by_group[gid]
                    group_name_cache[gid] = await get_user_group_nickname(
                        gsubs[0].bot_id, gsubs[0].user_id, gid
                    )

                # 优先从 store API 获取中文名，GetPlayerAchievements 的 gameName 始终为英文
                try:
                    game_info = await get_game_info(appid)
                    game_name = (
                        game_info.get("data", {}).get("name", "")
                        if game_info and game_info.get("success")
                        else ""
                    )
                except Exception:
                    game_name = ""
                game_name = game_name or new_archivement_info.get('gameName', '未知游戏')

                gamer_info = json.loads(await SteamIDInfo.get_steamuserinfo(steamid64) or "{}")
                gamer_name = gamer_info.get("personaname", steamid64)
                gamer_img_url = gamer_info.get("avatarfull", "")
                avatar_frame_url = await get_user_static_avatar_frame(steamid64)
                friend_code = steamid64_to_friend_code(steamid64)

                user_data = {
                    "name": gamer_name,
                    "friend_code": friend_code,
                    "avatar_url": gamer_img_url,
                    "avatar_frame_url": avatar_frame_url,
                    "bg_url": None,
                }

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
                        achievement_data = {
                            "game_name": game_name,
                            "name": archivement_name,
                            "description": archivement_desc,
                            "icon_url": archivement_img_url,
                        }
                        img_bytes = await render_achievement_push(
                            user_data=user_data,
                            achievement_data=achievement_data,
                        )
                        if img_bytes:
                            send_msg = MessageSegment.image(img_bytes)
                    except Exception as error:
                        logger.warning(
                            f"[SteamPoll] 成就图片渲染失败 appid={appid} steamid={steamid64}: {error!r}"
                        )

                    if send_msg is None:
                        send_msg = text_msg

                    for group_id, group_subs in push_subs_by_group.items():
                        for sub in group_subs:
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
                logger.warning(
                    f"[SteamPoll] 处理用户成就失败 steamid={steamid64} appid={appid}: {error!r}"
                )
                continue
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

        # 获取游戏名称、简介与封面图
        game_name = appid
        game_desc = ""
        cover_url = SteamAPI.GetGameCoverImageURL(appid, "header")
        try:
            game_data = await get_game_info(appid)
            if game_data and game_data.get("success"):
                d = game_data.get("data", {})
                game_name = d.get("name", appid)
                game_desc = d.get("short_description", "")
                cover_url = d.get("header_image") or cover_url
        except Exception as e:
            logger.warning(f"[SteamPoll] 降价推送获取游戏详情异常 appid={appid}: {e}")

        discount_percent = new_overview.get("discount_percent", 0)
        original_price = new_overview.get("initial_formatted") or old_overview.get("final_formatted", "")
        final_price = new_overview.get("final_formatted", "")

        # 优先使用 Playwright 渲染降价卡片
        img_bytes = None
        try:
            img_bytes = await render_game_price_drop(
                game_name=game_name,
                game_desc=game_desc,
                cover_url=cover_url,
                discount_percent=discount_percent,
                original_price=original_price,
                final_price=final_price,
            )
        except Exception as error:
            logger.warning(f"[SteamPoll] 渲染降价卡片失败 appid={appid}: {error!r}")

        # 向每个订阅者发送推送消息
        for sub in subs:
            try:
                if img_bytes:
                    send_msg = [
                        MessageSegment.at(sub.user_id),
                        MessageSegment.text("\n[Steam 降价订阅] 您订阅的游戏降价了！\n"),
                        MessageSegment.image(img_bytes),
                        MessageSegment.text(f"商店链接：https://store.steampowered.com/app/{appid}"),
                    ]
                else:
                    send_msg = [
                        MessageSegment.at(sub.user_id),
                        MessageSegment.text(
                            f"\n[Steam 降价订阅] 您订阅的游戏降价了！\n"
                            f"游戏：{game_name}\n"
                            f"原价：{original_price}\n"
                            f"现价：{final_price}\n"
                            f"折扣：-{discount_percent}%\n"
                            f"商店链接：https://store.steampowered.com/app/{appid}"
                        ),
                    ]
                await sub.send(send_msg)
            except Exception as error:
                logger.warning(
                    f"[SteamPoll] 推送降价失败 appid={appid}, user_id={sub.user_id}: {error!r}"
                )



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


#-----------------------------------------------------
# 游戏公告轮询
#-----------------------------------------------------

async def poll_and_push_game_announce() -> None:
    """游戏公告轮询主入口：拉取最新公告、检测更新、推送、记录基线。"""
    try:
        all_subs_info = await SteamAnnounceInfo.get_all_announce_subs()
        if not all_subs_info:
            return

        for info in all_subs_info:
            appid = info.appid
            if not appid:
                continue

            try:
                announcements = await get_game_announcements(appid, count=1)
            except Exception as error:
                logger.warning(f"[SteamPoll] 拉取公告失败 appid={appid}: {error!r}")
                continue

            if not announcements:
                continue

            latest = announcements[0]
            latest_gid = latest.get("gid", "")
            latest_time = latest.get("post_time", 0)

            # 首次未记录基线时更新基线但不推送；已有基线且 GID 或时间戳更新时推送
            if not info.last_gid and info.last_time == 0:
                await SteamAnnounceInfo.update_announce_data(appid, latest_gid, latest_time)
                continue

            if info.last_gid and latest_gid == info.last_gid:
                continue

            # 检测到新公告，查找订阅者
            subs = await gs_subscribe.get_subscribe(
                task_name="订阅steam游戏公告",
                uid=appid,
            )
            if not subs:
                continue

            # 获取游戏名称与封面
            game_name = appid
            game_logo_url = SteamAPI.GetGameCoverImageURL(appid, "header")
            try:
                game_data = await get_game_info(appid)
                if game_data and game_data.get("success"):
                    d = game_data.get("data", {})
                    game_name = d.get("name", appid)
                    game_logo_url = d.get("header_image") or game_logo_url
            except Exception as e:
                logger.warning(f"[SteamPoll] 拉取游戏信息异常 appid={appid}: {e}")

            # 渲染公告卡片
            try:
                img_bytes = await render_game_announce(
                    announce_item=latest,
                    appid=appid,
                    game_name=game_name,
                    game_logo_url=game_logo_url,
                )
            except Exception as error:
                logger.warning(f"[SteamPoll] 渲染公告卡片失败 appid={appid}: {error!r}")
                continue

            # 向所有订阅者发送推送消息并 AT
            for sub in subs:
                try:
                    send_msg = [
                        MessageSegment.at(sub.user_id),
                        MessageSegment.text(f"\n[Steam 公告订阅]{game_name} 发布了新公告\n"),
                        MessageSegment.image(img_bytes),
                        MessageSegment.text(f"公告链接: {latest['url']}"),
                    ]
                    await sub.send(send_msg)
                except Exception as error:
                    logger.warning(
                        f"[SteamPoll] 推送公告失败 appid={appid}, user_id={sub.user_id}: {error!r}"
                    )

            # 更新基线数据
            await SteamAnnounceInfo.update_announce_data(appid, latest_gid, latest_time)

    except Exception as error:
        logger.warning(f"[SteamPoll] 游戏公告轮询异常: {error!r}")

