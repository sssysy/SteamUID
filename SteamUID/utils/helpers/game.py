"""游戏元数据相关的公共解析。"""

from __future__ import annotations


def total_playtime(game: dict) -> int:
    """取单款游戏的累计游玩分钟数。"""
    return game.get("playtime_forever", 0) or (
        game.get("playtime_windows_forever", 0)
        + game.get("playtime_mac_forever", 0)
        + game.get("playtime_linux_forever", 0)
        + game.get("playtime_deck_forever", 0)
    )
