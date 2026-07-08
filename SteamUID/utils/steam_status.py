from ..SteamConfig import SteamConfig

PUSH_EVENTS: dict[str, str] = {
    "push_start_game": "开始游戏",
    "push_end_game": "结束游戏",
    "push_archivement": "获得成就",
}


def get_enabled_push_events() -> set[str]:
    return set(SteamConfig.get_config("PushSwitch").data)


def is_push_event_enabled(event_name: str) -> bool:
    return event_name in get_enabled_push_events()


def resolve_player_status(player: dict) -> tuple[str, str | None]:
    """返回 (status, game_name): ingame/offline/online"""
    if player.get("gameid"):
        return ("ingame", player.get("gameextrainfo", ""))
    if player.get("personastate", 0) == 0:
        return ("offline", None)
    return ("online", None)
