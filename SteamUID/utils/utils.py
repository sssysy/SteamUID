def auto2steamid64(count: str) -> str:
    """把好友码/steamid64自动变化成steamid64"""
    BASE_STEAM_ID64 = 76561197960265728
    if int(count) < BASE_STEAM_ID64:
        count = str(BASE_STEAM_ID64 + int(count))
    return count
