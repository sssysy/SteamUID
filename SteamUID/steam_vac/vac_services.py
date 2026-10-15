"""steamvac：取封禁汇总与昵称，拼成给用户的文本。"""

import asyncio
import datetime
from collections.abc import Sequence

from ..steam_config import SteamConfig
from ..utils.api.models import PlayerSummary
from ..utils.helper.steamid import steamid64_to_friend_code
from ..utils.helper.steam_api import fetch_player_bans, fetch_player_summaries

# 官方只给了 none / probation 两个示例，其余取值原样展示不做翻译
_ECONOMY_TEXT: dict[str, str] = {
    "probation": "限制",
    "banned": "封禁",
}


def _nickname(players: Sequence[PlayerSummary], steamid64: str) -> str:
    """昵称取人物摘要，取不到时回落好友码。"""
    if players and "personaname" in players[0] and players[0]["personaname"]:
        return players[0]["personaname"]
    return steamid64_to_friend_code(steamid64)


def _economy_line(raw: str) -> str:
    """经济封禁行；无封禁记录时不出这一行。"""
    if not raw or raw == "none":
        return ""
    if raw in _ECONOMY_TEXT:
        return f"经济封禁：{_ECONOMY_TEXT[raw]}"
    return f"经济封禁：{raw}"


def _last_ban_line(days: int, total_bans: int) -> str:
    """最后封禁时间行；无封禁记录时不出这一行。

    接口只回距最近一次封禁的天数，日期是按今天倒推出来的。
    """
    if total_bans <= 0:
        return ""
    date = datetime.date.today() - datetime.timedelta(days=days)
    return f"最后封禁时间：{date.isoformat()} (距今 {days} 天)"


async def build_ban_text(steamid64: str) -> str:
    """查询入口：封禁汇总与昵称并发取回，再拼文本。"""
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")
    cooldown = SteamConfig.get_config("KeyPoolCooldown").data

    bans, players = await asyncio.gather(
        fetch_player_bans(steamid64, keys=keys, cooldown=cooldown),
        fetch_player_summaries([steamid64], keys=keys, cooldown=cooldown),
    )
    if not bans:
        raise ValueError("未找到该 Steam 用户")

    ban = bans[0]
    community_banned = ban["CommunityBanned"] if "CommunityBanned" in ban else False
    vac_banned = ban["VACBanned"] if "VACBanned" in ban else False
    vac_count = ban["NumberOfVACBans"] if "NumberOfVACBans" in ban else 0
    game_count = ban["NumberOfGameBans"] if "NumberOfGameBans" in ban else 0
    days = ban["DaysSinceLastBan"] if "DaysSinceLastBan" in ban else 0

    lines = [
        f"[Steam] 玩家 {_nickname(players, steamid64)} 封禁情况：",
        f"社区封禁状态：{'是' if community_banned else '否'}",
        _economy_line(ban["EconomyBan"] if "EconomyBan" in ban else ""),
        f"VAC 封禁状态：{'是' if vac_banned else '否'}",
        f"VAC 封禁次数：{vac_count} 次",
        f"被封禁游戏数量：{game_count} 个",
        _last_ban_line(days, vac_count + game_count),
    ]
    return "\n".join(line for line in lines if line)
