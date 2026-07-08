import json

from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment
from PIL import Image

from ..utils.api import (
    get_user_Summaries,
    get_game_info,
    get_archivement_info,
    get_archivement_img,
)
from ..utils.database.models import (
    SteamIDInfo,
    SteamBind,
    SteamArchivementInfo,
)
from ..utils.PIL.draw import draw_game_status_photo, draw_archivements_photo
from ..utils.steam_status import (
    PUSH_EVENTS,
    get_enabled_push_events,
    is_push_event_enabled,
)


async def detect_status_changes(resp) -> tuple[list, list]:
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
            is_playing, appid, info, old_info, game_avatar
        )
        await _update_achievement_tracking(is_playing, appid, steamid64, enabled_events)
        await _dispatch_to_subs(subs, send_msg, push_column, steamid64)


async def _render_game_status_message(is_playing, appid, info, old_info, game_avatar):
    if is_playing:
        game_name = info.get("gameextrainfo")
        text_msg = f"{info.get('personaname')} 正在玩 {game_name}"
    else:
        game_name = old_info.get("gameextrainfo")
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
    for sub in subs:
        if not getattr(sub, push_column):
            continue
        try:
            await sub.send(send_msg)
        except Exception as error:
            logger.warning(f"[SteamPoll] 推送 steamid={steamid64} 失败: {error!r}")


async def flush_status_updates(update_list) -> None:
    for steamid64, info in update_list:
        await SteamIDInfo.upsert_steamuserinfo(
            steamid64, json.dumps(info, ensure_ascii=False)
        )


async def poll_and_push_game_status() -> None:
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
        await flush_status_updates(update_list)
    except Exception as error:
        logger.warning(f"[SteamPoll] 游戏状态轮询失败: {error!r}")


async def poll_and_push_achievements() -> None:
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
