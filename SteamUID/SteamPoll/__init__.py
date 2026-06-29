from gsuid_core.logger import logger
from gsuid_core.aps import scheduler
from gsuid_core.subscribe import gs_subscribe
from ..utils.database.models import SteamIDInfo
from .api import get_user_Summaries
import json
from ..SteamConfig import SteamConfig


# 订阅主题（与 SteamBind/__init__.py 保持一致）
STEAM_POLL_TASK = "SteamPoll"


@scheduler.scheduled_job(
    'interval',
    seconds=SteamConfig.get_config("PollInterval").data,
)
async def get_user_Summaries_job():
    # 无绑定时跳过，避免无意义请求
    steamid_all = await SteamIDInfo.get_all_steamid64()
    if not steamid_all:
        return

    resp = await get_user_Summaries(steamid_all)

    push_list = []
    for info in resp:
        steamid64 = info.get("steamid")
        if not steamid64:
            # 缺字段跳过，避免污染缓存
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

    # 推送逻辑移出 for info 循环，避免重复推送
    for item in push_list:
        steamid64 = item.get("steamid")
        # 反查该 steamid64 的所有订阅者（订阅系统自动处理路由）
        subs = await gs_subscribe.get_subscribe(STEAM_POLL_TASK, uid=steamid64)
        if not subs:
            continue

        if item.get("gameid", ""):
            send_msg = f"{item.get('personaname')} 正在玩 {item.get('gameextrainfo')}"
        else:
            send_msg = f"{item.get('personaname')} 结束游戏"

        for sub in subs:
            try:
                await sub.send(send_msg)
            except Exception as error:
                logger.warning(f"[SteamPoll] 推送 steamid={steamid64} 失败: {error!r}")
