from io import BytesIO

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment, pic_quality

from ..utils.database.models import SteamBind
from ..utils.api import (
    get_archivement_info,
    get_archivement_schema,
    get_user_Summaries,
)
from ..utils.PIL.draw import draw_archivement_info, draw_user_info_head

SV = SV("steam成就服务")


@SV.on_command("游戏成就")
async def game_archivements(bot: Bot, ev: Event):
    appid = ev.text.strip()
    if not appid:
        await bot.send("请携带appid！")
        return

    if ev.at:
        ev.user_id = ev.at

    # steamid64 仅从绑定获取（text 是 appid 不是 steamid64）
    steamid64 = await SteamBind.get_main_id(
        ev.bot_id, ev.user_id, ev.user_type, ev.group_id
    )
    if not steamid64:
        return await bot.send("请先绑定 steam 账号")

    # 1) 获取玩家成就解锁列表
    try:
        playerstats = await get_archivement_info(appid, steamid64)
    except Exception as e:
        logger.warning(f"[游戏成就] 拉取玩家成就失败 appid={appid}: {e!r}")
        return await bot.send(f"获取玩家成就失败: {e}")

    achievements = playerstats.get("achievements")
    if not achievements:
        return await bot.send("未获取到成就数据，可能该游戏无成就或 steam 资料未公开")

    # 2) 一次性获取 schema（含 icon/icongray）
    try:
        schema_list = await get_archivement_schema(appid)
    except Exception as e:
        logger.warning(f"[游戏成就] 拉取成就 schema 失败 appid={appid}: {e!r}")
        return await bot.send(f"获取成就图标失败: {e}")

    # schema 以 name(=apiname) 为 key 建索引
    schema_map = {s.get("name"): s for s in schema_list}

    # 3) 组装 (图片URL, 成就名, 成就简介) 元组
    unlocked_list: list[tuple[str, str, str]] = []
    locked_list: list[tuple[str, str, str]] = []
    for ach in achievements:
        apiname = ach.get("apiname", "")
        achieved = ach.get("achieved") == 1
        s = schema_map.get(apiname, {})
        # 已解锁用 icon，未解锁用 icongray（直接用 API 提供的灰图）
        icon_url = s.get("icon", "") if achieved else s.get("icongray", "")
        # 成就名优先取 playerstats.name，回退 schema displayName
        name = ach.get("name") or s.get("displayName", "") or apiname
        desc = ach.get("description") or s.get("description", "") or ""
        if achieved:
            unlocked_list.append((icon_url, name, desc))
        else:
            locked_list.append((icon_url, name, desc))

    if not unlocked_list and not locked_list:
        return await bot.send("该游戏暂无成就数据")

    game_name = playerstats.get("gameName", "") or appid

    # 4) 绘制成就列表图
    try:
        img = await draw_archivement_info(game_name, unlocked_list, locked_list)
    except Exception as e:
        logger.warning(f"[游戏成就] 绘图失败 appid={appid}: {e!r}")
        return await bot.send(f"成就图片渲染失败: {e}")

    # 5) 获取玩家摘要，套上用户信息头
    try:
        players = await get_user_Summaries(steamid64)
        player = players[0] if players else {}
    except Exception as e:
        logger.warning(f"[游戏成就] 拉取玩家摘要失败 steamid={steamid64}: {e!r}")
        player = {}

    user_name = player.get("personaname", steamid64)
    user_avatar = player.get("avatarfull", "")
    # 状态映射：有 gameid → ingame，personastate==0 → offline，其余 → online
    if player.get("gameid"):
        user_status = "ingame"
        status_game = player.get("gameextrainfo", "")
    elif player.get("personastate", 0) == 0:
        user_status = "offline"
        status_game = None
    else:
        user_status = "online"
        status_game = None
        
    # 6) 发送图片
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=pic_quality, subsampling=0)
    await bot.send(MessageSegment.image(buf.getvalue()))
