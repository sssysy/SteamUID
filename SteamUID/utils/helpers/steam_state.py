"""Steam 状态枚举常量，统一「字段缺失时的默认值」与状态映射。"""

# communityvisibilitystate
VISIBILITY_PRIVATE = 1
VISIBILITY_FRIENDS_ONLY = 2
VISIBILITY_PUBLIC = 3

# personastate
PERSONA_STATE_OFFLINE = 0

# 绘图层的 status 类名（与 CSS 中的 .status_* 对应）
STATUS_INGAME = "ingame"
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"

# personastate → (persona_class, status_class, status_text)
# 覆盖全部合法取值（0 为离线），映射表自身自洽，不依赖调用方先做 0 拦截。
STATUS_MAP: dict[int, tuple[str, str, str]] = {
    0: ("offline", "offline", "离线"),
    1: ("online", "online", "在线"),
    2: ("online", "online", "忙碌"),
    3: ("online", "online", "离开"),
    4: ("online", "online", "打盹"),
    5: ("online", "online", "想交易"),
    6: ("online", "online", "想游玩"),
}

# Steam 以后新增 personastate 时的兜底形态（视为在线）
_DEFAULT_STATUS = ("online", "online", "在线")


def get_persona_status(personastate: int | None) -> tuple[str, str, str]:
    """把 personastate 解析为 (persona_class, status_class, status_text)。"""
    return STATUS_MAP.get(personastate or 0, _DEFAULT_STATUS)


def resolve_player_status(player: dict) -> tuple[str, str | None]:
    """从 GetPlayerSummaries 单条数据解析 ``(status, game_name)``。

    status 取 ``STATUS_INGAME`` / ``STATUS_ONLINE`` / ``STATUS_OFFLINE``；
    在游戏中时 game_name 为游戏名（可能为空串）。
    """
    if player.get("gameid"):
        return (STATUS_INGAME, player.get("gameextrainfo", ""))
    if player.get("personastate", 0) == PERSONA_STATE_OFFLINE:
        return (STATUS_OFFLINE, None)
    return (STATUS_ONLINE, None)
