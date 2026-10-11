"""用户状态的领域模型、推送词表与纯比对逻辑。

只推导事件与编解码基线，不碰数据库、网络与配置，便于直接单测。
推送选项也放这里，供配置层组装后注入推送层，避免 utils 反向依赖配置。
"""

from typing import Literal, TypedDict
from dataclasses import dataclass, field

import msgspec

from ..api.models import PlayerAchievement, PlayerSummary

# 成就事件：同一玩家同一游戏的成就往下拼成一张卡，其余事件一个一张卡
ACHIEVEMENT_KIND = "获得成就"

# 通知类型的唯一来源：配置项、订阅任务名与事件类型都取自这里
NOTIFY_KINDS: tuple[str, ...] = (
    "开始游戏",
    "结束游戏",
    ACHIEVEMENT_KIND,
    "用户上线",
    "用户离线",
)

StatusEventKind = Literal["开始游戏", "结束游戏", "获得成就", "用户上线", "用户离线"]

# 推送方式词表：分离/合并与文字/图片正交，靠下面两个集合判定
PUSH_MODES: tuple[str, ...] = ("纯文字分离", "纯文字合并", "图片分离", "图片合并")
DEFAULT_PUSH_MODE = "图片分离"
IMAGE_MODES: frozenset[str] = frozenset(("图片分离", "图片合并"))
MERGE_MODES: frozenset[str] = frozenset(("纯文字合并", "图片合并"))
# 需要游戏封面与游戏名的一类事件
GAME_KINDS: frozenset[str] = frozenset(("开始游戏", "结束游戏"))
# 出图的事件类型：每种通知都有对应卡片
CARD_KINDS: frozenset[str] = frozenset(NOTIFY_KINDS)


def is_image_mode(mode: str) -> bool:
    """推送方式是否出图。"""
    return mode in IMAGE_MODES


def is_merge_mode(mode: str) -> bool:
    """推送方式是否把一轮变化合并成一条消息。"""
    return mode in MERGE_MODES


@dataclass(frozen=True)
class PushOptions:
    """一次推送所需的全局选项，由调用方从配置读出后注入。"""

    kinds: frozenset[str]
    cd_seconds: int
    mode: str
    with_cover: bool
    region_cc: str
    griddb_key: str


@dataclass(frozen=True)
class AchievementUnlock:
    """新解锁的一条成就：名称、介绍、图标 URL 与解锁时间戳。"""

    name: str = ""
    description: str = ""
    icon: str = ""
    time: int = 0


@dataclass(frozen=True)
class UserStatusEvent:
    """一次比对产出的待通知事件。"""

    kind: StatusEventKind
    steamid64: str
    ts: int
    nickname: str
    appid: str = ""
    game_name: str = ""
    achievement: AchievementUnlock = field(default_factory=AchievementUnlock)
    avatar: str = ""


class StatusSnapshot(TypedDict, total=False):
    """状态基线，只存比对与文案需要的字段。"""

    gameid: str
    gameextrainfo: str
    personastate: int
    personaname: str
    avatarfull: str


def to_snapshot(player: PlayerSummary) -> StatusSnapshot:
    """从玩家摘要提取基线字段，缺失的字段不进快照。"""
    snapshot = StatusSnapshot()
    if "gameid" in player:
        snapshot["gameid"] = player["gameid"]
    if "gameextrainfo" in player:
        snapshot["gameextrainfo"] = player["gameextrainfo"]
    if "personaname" in player:
        snapshot["personaname"] = player["personaname"]
    if "personastate" in player:
        snapshot["personastate"] = player["personastate"]
    if "avatarfull" in player:
        snapshot["avatarfull"] = player["avatarfull"]
    return snapshot


def snapshot_to_json(snapshot: StatusSnapshot) -> str:
    return msgspec.json.encode(snapshot).decode()


def snapshot_from_json(raw: str) -> StatusSnapshot:
    """解析基线 JSON；结构非法时抛 msgspec.ValidationError。"""
    return msgspec.json.decode(raw, type=StatusSnapshot)


def names_to_json(names: list[str]) -> str:
    return msgspec.json.encode(names).decode()


def names_from_json(raw: str) -> list[str]:
    """解析已解锁成就基线；结构非法时抛 msgspec.ValidationError。"""
    return msgspec.json.decode(raw, type=list[str])


def diff_status(
    steamid64: str,
    prev: StatusSnapshot | None,
    cur: StatusSnapshot,
    ts: int,
) -> list[UserStatusEvent]:
    """比对前后基线产出事件；无基线时只建基线、不产事件。

    仅当两侧都带 personastate 才判上下线，避免私密资料缺字段造成误报。
    """
    if prev is None:
        return []

    cur_name = cur["personaname"] if "personaname" in cur else ""
    prev_name = prev["personaname"] if "personaname" in prev else ""
    nickname = cur_name or prev_name
    avatar = cur["avatarfull"] if "avatarfull" in cur else ""
    events: list[UserStatusEvent] = []

    prev_game = prev["gameid"] if "gameid" in prev else ""
    cur_game = cur["gameid"] if "gameid" in cur else ""
    if prev_game != cur_game:
        if prev_game:
            prev_title = prev["gameextrainfo"] if "gameextrainfo" in prev else ""
            events.append(
                UserStatusEvent(
                    kind="结束游戏",
                    steamid64=steamid64,
                    ts=ts,
                    nickname=nickname,
                    appid=prev_game,
                    game_name=prev_title,
                    avatar=avatar,
                )
            )
        if cur_game:
            cur_title = cur["gameextrainfo"] if "gameextrainfo" in cur else ""
            events.append(
                UserStatusEvent(
                    kind="开始游戏",
                    steamid64=steamid64,
                    ts=ts,
                    nickname=nickname,
                    appid=cur_game,
                    game_name=cur_title,
                    avatar=avatar,
                )
            )

    if "personastate" in prev and "personastate" in cur:
        prev_online = prev["personastate"] != 0
        cur_online = cur["personastate"] != 0
        if prev_online != cur_online:
            events.append(
                UserStatusEvent(
                    kind="用户上线" if cur_online else "用户离线",
                    steamid64=steamid64,
                    ts=ts,
                    nickname=nickname,
                    avatar=avatar,
                )
            )
    return events


def unlocked_names(entries: list[PlayerAchievement]) -> list[str]:
    """已解锁成就的 apiname，保持接口返回顺序。"""
    names: list[str] = []
    for entry in entries:
        if "apiname" not in entry:
            continue
        if "achieved" in entry and entry["achieved"]:
            names.append(entry["apiname"])
    return names


def diff_achievements(prev: set[str], entries: list[PlayerAchievement]) -> list[str]:
    """相对基线新解锁的 apiname。"""
    fresh: list[str] = []
    for name in unlocked_names(entries):
        if name not in prev:
            fresh.append(name)
    return fresh
