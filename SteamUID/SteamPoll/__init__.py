from gsuid_core.logger import logger
from gsuid_core.aps import scheduler
from ..utils.database.models import SteamIDInfo, SteamBind
from ..utils.api import get_user_Summaries
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
        elif old_info.get("gameid", ""):
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

        if info.get("gameid", ""):
            # 开始游戏
            appid = info.get("gameid")
            game_data = game_info_map.get(appid, {})
            game_avatar = game_data.get("header_image")
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
        else:
            # 结束游戏
            appid = old_info.get("gameid", "")
            game_data = game_info_map.get(appid, {})
            game_avatar = game_data.get("header_image")
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

        for sub in subs:
            try:
                await sub.send(send_msg)
            except Exception as error:
                logger.warning(f"[SteamPoll] 推送 steamid={steamid64} 失败: {error!r}")

    # 推送完成后写入数据库
    for steamid64, info in update_list:
        await SteamIDInfo.upsert_steamuserinfo(
            steamid64, json.dumps(info, ensure_ascii=False)
        )
