from gsuid_core.logger import logger
from gsuid_core.aps import scheduler
from ..utils.database.models import SteamIDInfo, SteamBind
from ..utils.api import get_user_Summaries
import json
from ..SteamConfig import SteamConfig
from ..utils.PIL.draw import draw_start_game_photo
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

    push_list = []
    for info in resp:
        steamid64 = info.get("steamid")
        if not steamid64:
            continue

        old_info = json.loads(await SteamIDInfo.get_steamuserinfo(steamid64) or "{}")

        # 信息有变化才更新缓存
        if info != old_info:
            await SteamIDInfo.upsert_steamuserinfo(
                steamid64, json.dumps(info, ensure_ascii=False)
            )

            # 游戏状态变化才推送
            if info.get("gameid", "") != old_info.get("gameid", ""):
                push_list.append(info)

    # 预取所有 appid 的游戏信息
    appids = {item.get("gameid") for item in push_list if item.get("gameid", "")}
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
    for item in push_list: # item -> appidinfo
        steamid64 = item.get("steamid")
        # 反查该 steamid64 的所有绑定者
        subs = await SteamBind.get_bind_by_steamid(steamid64)
        if not subs:
            continue

        if item.get("gameid", ""):
            appid = item.get("gameid")
            game_data = game_info_map.get(appid, {})
            game_avatar = game_data.get("header_image")
            try:
                IMG = await draw_start_game_photo(
                    appid=appid,
                    game_name=item.get("gameextrainfo"),
                    avatar_url=item.get("avatarfull"),
                    avatar_hash=item.get("avatarhash"),
                    username=item.get("personaname"),
                    game_background=game_avatar,
                )
            except Exception as error:
                logger.warning(f"[SteamPoll] 绘图失败 appid={appid}: {error!r}")
                IMG = None
            if isinstance(IMG, Image.Image):
                send_msg = MessageSegment.image(IMG)
            else:
                send_msg = f"{item.get('personaname')} 正在玩 {item.get('gameextrainfo')}"
        else:
            send_msg = f"{item.get('personaname')} 结束游戏"

        for sub in subs:
            try:
                await sub.send(send_msg)
            except Exception as error:
                logger.warning(f"[SteamPoll] 推送 steamid={steamid64} 失败: {error!r}")
