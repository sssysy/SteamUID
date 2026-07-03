from gsuid_core.logger import logger
from gsuid_core.aps import scheduler
from ..utils.database.models import SteamIDInfo, SteamBind, SteamArchivementInfo
from ..utils.api import get_user_Summaries, get_archivement_info
import json
from ..SteamConfig import SteamConfig
from ..utils.PIL.draw import draw_start_game_photo, draw_end_game_photo
from ..utils.api import get_game_info
from PIL import Image
from gsuid_core.segment import MessageSegment


@scheduler.scheduled_job(
    'interval',
    seconds=SteamConfig.get_config("PollInterval").data,
)
async def get_user_Summaries_job():
    # 开始关闭游戏推送没开启直接返回，防止无用请求
    push_switch = SteamConfig.get_config("PushSwitch").data
    if "开始游戏" not in push_switch and "结束游戏" not in push_switch:
        return

    steamid_all = await SteamIDInfo.get_all_steamid64()
    if not steamid_all:
        return

    try:
        resp = await get_user_Summaries(steamid_all)
    except Exception as error:
        logger.warning(f"[SteamPoll] 拉取玩家摘要失败: {error!r}")
        return

    push_list = []      # 游戏状态变化需要推送的 (info, old_info)
    update_list = []    # 所有信息有变化需要更新缓存的 (steamid64, info)
    for info in resp:
        steamid64 = info.get("steamid")
        if not steamid64:
            continue

        old_info = json.loads(await SteamIDInfo.get_steamuserinfo(steamid64) or "{}")

        # 信息有变化才更新缓存
        if info != old_info:
            update_list.append((steamid64, info))
            # 游戏状态变化才推送
            if info.get("gameid", "") != old_info.get("gameid", ""):
                push_list.append((info, old_info))

    # 预取所有 appid 的游戏信息（含开始与结束的游戏）
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

    # 推送逻辑移出 for info 循环，避免重复推送
    for info, old_info in push_list:
        steamid64 = info.get("steamid")
        # 反查该 steamid64 的所有绑定者
        subs = await SteamBind.get_bind_by_steamid(steamid64)
        if not subs:
            continue
        
        is_playing = bool(info.get("gameid", ""))
        appid = info.get("gameid") if is_playing else old_info.get("gameid", "")
        game_data = game_info_map.get(appid, {})
        game_avatar = game_data.get("header_image")

        # 提前判断是否有用户需要推送，避免无效渲染
        push_switch = set(SteamConfig.get_config("PushSwitch").data)
        target_event = "开始游戏" if is_playing else "结束游戏"
        if target_event not in push_switch:
            continue
        push_column = "push_start_game" if is_playing else "push_end_game"
        if not any(getattr(sub, push_column) for sub in subs):
            continue

        if is_playing:
            # 开始游戏
            try:
                IMG = await draw_start_game_photo(
                    appid=appid,
                    game_name=info.get("gameextrainfo"),
                    avatar_url=info.get("avatarfull"),
                    avatar_hash=info.get("avatarhash"),
                    username=info.get("personaname"),
                    game_background=game_avatar,
                )
            except Exception as error:
                logger.warning(f"[SteamPoll] 绘图失败 appid={appid}: {error!r}")
                IMG = None
            if isinstance(IMG, Image.Image):
                send_msg = MessageSegment.image(IMG)
            else:
                send_msg = f"{info.get('personaname')} 正在玩 {info.get('gameextrainfo')}"
            
            # 添加到成就轮询列表
            if "获得成就" in SteamConfig.get_config("PushSwitch").data:
                try:
                    resp = await get_archivement_info(appid, steamid64)
                    await SteamArchivementInfo.upsert_archivement_data(
                        steamid64,
                        appid,
                        json.dumps(resp, ensure_ascii=False)
                    )
                except Exception as error:
                    logger.warning(f"[SteamPoll] 拉取成就初始数据失败 appid={appid} steamid={steamid64}: {error!r}")
                
        else:
            # 结束游戏
            try:
                IMG = await draw_end_game_photo(
                    appid=appid,
                    game_name=old_info.get("gameextrainfo"),
                    avatar_url=info.get("avatarfull"),
                    avatar_hash=info.get("avatarhash"),
                    username=info.get("personaname"),
                    game_background=game_avatar,
                )
            except Exception as error:
                logger.warning(f"[SteamPoll] 绘图失败 appid={appid}: {error!r}")
                IMG = None
            if isinstance(IMG, Image.Image):
                send_msg = MessageSegment.image(IMG)
            else:
                send_msg = f"{info.get('personaname')} 结束游戏 {old_info.get('gameextrainfo')}"

            # 从成就轮询列表中移除
            if "获得成就" in SteamConfig.get_config("PushSwitch").data:
                await SteamArchivementInfo.delete_archivement_data(steamid64)
                
        for sub in subs:
            if is_playing and not sub.push_start_game:
                continue
            if not is_playing and not sub.push_end_game:
                continue
            try:
                await sub.send(send_msg)
            except Exception as error:
                logger.warning(f"[SteamPoll] 推送 steamid={steamid64} 失败: {error!r}")



    # 推送完成后写入数据库
    for steamid64, info in update_list:
        await SteamIDInfo.upsert_steamuserinfo(
            steamid64, json.dumps(info, ensure_ascii=False)
        )

@scheduler.scheduled_job(
    'interval',
    seconds=SteamConfig.get_config("ArchivementsPollInterval").data,
)
async def check_archivement():
    """查询Steam成就记录"""
    # 开始关闭游戏推送没开启直接返回，防止无用请求
    push_switch = SteamConfig.get_config("PushSwitch").data
    if "获得成就" not in push_switch:
        return

    steamid_all = await SteamArchivementInfo.get_all_archivement_info()
    if not steamid_all:
        return
    
    for steamid in steamid_all:
        appid = steamid.appid
        steamid64 = steamid.steamid64

        try:
            resp = await get_archivement_info(appid, steamid64)
        except Exception as error:
            logger.warning(f"[SteamPoll] 拉取成就信息失败 appid={appid} steamid64={steamid64}:  {error!r}")
            continue
        
        old_archivement_info = json.loads(steamid.archivement_data)
        new_archivement_info = resp
        # 对比新旧成就，找出新解锁的
        old_achievements = {    
            a['apiname']: a
            for a in old_archivement_info.get('playerstats', {}).get('achievements', [])
        }
        newly_achieved = [
            a for a in new_archivement_info.get('playerstats', {}).get('achievements', [])
            if a.get('achieved') == 1
            and old_achievements.get(a['apiname'], {}).get('achieved') == 0
        ]

        if not newly_achieved:
            # 没有新成就，跳过
            continue

        # 获取绑定该 steamid 的用户并推送
        subs = await SteamBind.get_bind_by_steamid(steamid64)
        game_name = new_archivement_info.get('gameName', '未知游戏')

        for ach in newly_achieved:
            msg = (
                f"{steamid.steamid64} 解锁成就：\n"
                f"游戏：{game_name}\n"
                f"成就：{ach['name']}\n"
                f"描述：{ach['description']}"
            )
            for sub in subs:
                if not sub.push_archivement:
                    continue
                try:
                    await sub.send(msg)
                except Exception as error:
                    logger.warning(f"[SteamPoll] 推送成就失败 steamid={steamid64}: {error!r}")

        # 更新数据库
        await SteamArchivementInfo.upsert_archivement_data(
            steamid64, appid,
            json.dumps(new_archivement_info, ensure_ascii=False)
        )
