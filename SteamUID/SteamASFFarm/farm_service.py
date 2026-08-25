from __future__ import annotations

from typing import Any
from gsuid_core.models import Event

from ..utils.database.models import SteamBind
from ..utils.utils import auto2steamid64
from ..SteamASFLogin.login import _sanitize_bot_name


def format_timespan(time_str: str | None) -> str:
    """
    格式化 .NET TimeSpan 字符串 (例如 '01:30:00', '00:45:00', '1.04:30:00', '00:00:00')
    为人类可读的中文时长描述
    """
    if not time_str or time_str == "00:00:00":
        return "0分钟"

    time_str = time_str.strip()
    days = 0
    hours = 0
    minutes = 0
    seconds = 0

    main_part = time_str
    # 拆分天数 (例如 '1.04:30:00' 或 '2.10:00:00')
    if "." in time_str and ":" in time_str:
        parts = time_str.split(".", 1)
        if parts[0].isdigit() and ":" in parts[1]:
            days = int(parts[0])
            main_part = parts[1]

    # 拆分 hh:mm:ss (可能附带毫秒例如 '04:30:00.1234567')
    if ":" in main_part:
        if "." in main_part:
            main_part = main_part.split(".", 1)[0]
        hms = main_part.split(":")
        if len(hms) >= 3:
            try:
                hours = int(hms[0])
                minutes = int(hms[1])
                seconds = int(hms[2])
            except ValueError:
                return time_str
        elif len(hms) == 2:
            try:
                minutes = int(hms[0])
                seconds = int(hms[1])
            except ValueError:
                return time_str

    parts_txt = []
    if days > 0:
        parts_txt.append(f"{days}天")
    if hours > 0:
        parts_txt.append(f"{hours}小时")
    if minutes > 0:
        parts_txt.append(f"{minutes}分钟")
    if not parts_txt:
        if seconds > 0:
            parts_txt.append(f"{seconds}秒")
        else:
            return "0分钟"
    return "".join(parts_txt)


def parse_farming_data(bot_info: dict[str, Any]) -> dict[str, Any]:
    """解析 ASF Bot 的 CardsFarmer 挂卡状态与进度数据"""
    cards_farmer = bot_info.get("CardsFarmer") or {}
    paused = bool(cards_farmer.get("Paused", False))
    time_remaining_raw = str(cards_farmer.get("TimeRemaining") or "00:00:00")
    formatted_time = format_timespan(time_remaining_raw)

    current_games: list[dict[str, Any]] = cards_farmer.get("CurrentGamesFarming") or []
    games_to_farm: list[dict[str, Any]] = cards_farmer.get("GamesToFarm") or []

    # 汇总所有需要挂卡的游戏（以 AppID 去重）
    all_games_map: dict[int, dict[str, Any]] = {}
    for g in current_games + games_to_farm:
        appid = g.get("AppID")
        if appid:
            if appid not in all_games_map:
                all_games_map[appid] = g
            else:
                # 若重复取卡片数较多的一条
                if (g.get("CardsRemaining") or 0) > (all_games_map[appid].get("CardsRemaining") or 0):
                    all_games_map[appid] = g

    total_games_count = len(all_games_map)
    total_cards_count = sum(int(g.get("CardsRemaining") or 0) for g in all_games_map.values())

    return {
        "paused": paused,
        "time_remaining_raw": time_remaining_raw,
        "formatted_time": formatted_time,
        "current_games": current_games,
        "games_to_farm": games_to_farm,
        "total_games_count": total_games_count,
        "total_cards_count": total_cards_count,
        "all_games": list(all_games_map.values()),
    }


async def get_user_asf_target(ev: Event, text: str = "") -> tuple[str, str | None, bool]:
    """
    定位用户的 ASF 目标 Bot 与 SteamID64
    返回: (bot_name, steamid64, is_asf_bound)
    """
    steamid64 = auto2steamid64(text.strip()) if text.strip() else None

    user_binds = await SteamBind.get_binds_by_user(
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
        group_id=ev.group_id,
    )
    if not user_binds:
        user_binds = await SteamBind.get_binds_by_user(
            bot_id=ev.bot_id,
            user_id=ev.user_id,
            user_type=ev.user_type,
        )

    if not steamid64:
        # 优先查找当前绑定的主账号
        main_sid = await SteamBind.get_main_id(
            bot_id=ev.bot_id,
            user_id=ev.user_id,
            user_type=ev.user_type,
            group_id=ev.group_id,
        )
        if main_sid:
            steamid64 = main_sid
        elif len(user_binds) == 1:
            steamid64 = user_binds[0].steamid64

    # 检查是否有 ASF 绑定标记
    is_asf_bound = any(b.is_asf for b in user_binds)
    if steamid64:
        for b in user_binds:
            if b.steamid64 == steamid64 and b.is_asf:
                is_asf_bound = True
                break

    bot_name = _sanitize_bot_name(ev.user_id)
    return bot_name, steamid64, is_asf_bound
