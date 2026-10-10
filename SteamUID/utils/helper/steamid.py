"""SteamID 与好友码互转。"""

_BASE_STEAM_ID64 = 76561197960265728


def steamid64_to_friend_code(steamid64: str) -> str:
    """steamid64 转好友码（账号 ID）。"""
    return str(int(steamid64) - _BASE_STEAM_ID64)


def friend_code_to_steamid64(friend_code: str) -> str:
    """好友码（账号 ID）转 steamid64。"""
    return str(_BASE_STEAM_ID64 + int(friend_code))


def auto2steamid64(text: str) -> str | None:
    """把好友码或 steamid64 统一成 steamid64；空串或非数字返回 None。"""
    raw = text.strip()
    if not raw.isdigit():
        return None
    value = int(raw)
    if value >= _BASE_STEAM_ID64:
        return str(value)
    return str(_BASE_STEAM_ID64 + value)
