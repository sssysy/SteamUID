"""游戏库展示的纯逻辑：可见性过滤、时长排序与格子跨度。"""

from dataclasses import dataclass
from collections.abc import Sequence

# 游玩不足该分钟数的库内游戏不上墙（含从未启动的）
MIN_PLAYTIME_MINUTES = 10


@dataclass(frozen=True)
class LibraryGame:
    """墙上待展示的一款游戏。"""

    appid: str
    name: str
    playtime_minutes: int


def visible_games(games: Sequence[LibraryGame]) -> list[LibraryGame]:
    """过滤游玩过短的库内游戏，并按时长降序，玩得多的排在前面。"""
    played = [game for game in games if game.playtime_minutes >= MIN_PLAYTIME_MINUTES]
    played.sort(key=lambda game: game.playtime_minutes, reverse=True)
    return played


def span_of(playtime_minutes: int) -> int:
    """按游玩时长决定格子边长（1~4 格），玩得越多占得越大。"""
    hours = playtime_minutes / 60
    if hours > 1000:
        return 4
    if hours > 500:
        return 3
    if hours > 100:
        return 2
    return 1
