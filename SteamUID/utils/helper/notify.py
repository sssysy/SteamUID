"""状态事件的通知前置：订阅匹配、推送冷却与文案构造。

只做筛选、会话聚合与文案，渲染和发送交给上层推送层，避免 helper 反向依赖渲染层。
"""

import time
from dataclasses import dataclass, field
from collections import defaultdict
from collections.abc import Sequence

from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import CoreUser, Subscribe

from .status import PushOptions, UserStatusEvent

_SUBSCRIBE_PREFIX = "订阅Steam"

# (steamid64, group_id) -> 上次推送时间；仅临时内存态，重启即清空
_last_push_time: defaultdict[tuple[str, str], float] = defaultdict(float)


def subscribe_task_name(kind: str) -> str:
    """个人订阅任务名，如 订阅Steam开始游戏。"""
    return f"{_SUBSCRIBE_PREFIX}{kind}"


def cd_pass(steamid64: str, group_id: str | None, cd_seconds: int) -> bool:
    """群聊冷却判定；私聊与未配置冷却时恒通过。"""
    if not group_id or cd_seconds <= 0:
        return True
    return time.monotonic() - _last_push_time[(steamid64, group_id)] >= cd_seconds


def cd_mark(steamid64: str, group_id: str | None, cd_seconds: int) -> None:
    """推送成功后记一次冷却；私聊与未配置冷却不记。"""
    if not group_id or cd_seconds <= 0:
        return
    _last_push_time[(steamid64, group_id)] = time.monotonic()


def build_message(event: UserStatusEvent, group_name: str) -> str:
    """构造单条文案正文（不含 [Steam] 前缀）；游戏名缺失时回落 appid。"""
    game = event.game_name or event.appid or "未知游戏"
    name = event.nickname or event.steamid64
    display = f"{name}({group_name})"
    if event.kind == "开始游戏":
        return f"{display} 正在玩 {game}({event.appid})"
    if event.kind == "结束游戏":
        return f"{display} 已结束游玩 {game}({event.appid})"
    if event.kind == "获得成就":
        return f"{display} 在 {game}({event.appid}) 解锁了成就 {event.achievement.name}"
    if event.kind == "用户上线":
        return f"{display} 已上线"
    return f"{display} 已离线"


@dataclass(frozen=True)
class Delivery:
    """一个推送会话及其本轮内容，entries 为 (事件, 群名展示串)。"""

    sub: Subscribe
    entries: tuple[tuple[UserStatusEvent, str], ...]


@dataclass
class _Bucket:
    """会话聚合的中间态，seen 用于同一会话内多个订阅命中同一事件时去重。"""

    sub: Subscribe
    seen: set[tuple[str, str, str, str, int]] = field(default_factory=set)
    entries: list[tuple[UserStatusEvent, str]] = field(default_factory=list)


def _session_key(sub: Subscribe) -> tuple[str, str, str, str]:
    """群聊按群聚合，私聊按用户聚合。"""
    if sub.group_id:
        return ("group", sub.bot_id, sub.bot_self_id or "", sub.group_id)
    return ("direct", sub.bot_id, sub.bot_self_id or "", sub.user_id)


def _event_key(event: UserStatusEvent) -> tuple[str, str, str, str, int]:
    return (event.kind, event.steamid64, event.appid, event.achievement.name, event.ts)


async def _group_display(sub: Subscribe) -> str:
    """群名片优先，取不到回落用户 ID；私聊没有群名片，同样回落 ID。"""
    if not sub.group_id:
        return sub.user_id
    user = await CoreUser.base_select_data(
        bot_id=sub.bot_id, user_id=sub.user_id, group_id=sub.group_id
    )
    if user is not None and user.user_name and user.user_name != "1":
        return str(user.user_name)
    return sub.user_id


async def collect_deliveries(
    events: Sequence[UserStatusEvent], options: PushOptions
) -> list[Delivery]:
    """按 全局类型 -> 个人订阅 -> 冷却 过滤后，按推送会话聚合。"""
    grouped: dict[tuple[str, str, str, str], _Bucket] = {}
    for event in events:
        if event.kind not in options.kinds:
            continue
        # 框架订阅接口无类型标注，这里立刻收窄为 Subscribe
        raw = await gs_subscribe.get_subscribe(
            subscribe_task_name(event.kind), uid=event.steamid64
        )
        if not raw:
            continue
        for sub in raw:
            if not isinstance(sub, Subscribe):
                continue
            if not cd_pass(event.steamid64, sub.group_id, options.cd_seconds):
                continue
            key = _session_key(sub)
            if key in grouped:
                bucket = grouped[key]
            else:
                bucket = _Bucket(sub=sub)
                grouped[key] = bucket
            event_key = _event_key(event)
            if event_key in bucket.seen:
                continue
            bucket.seen.add(event_key)
            bucket.entries.append((event, await _group_display(sub)))
    return [Delivery(sub=bucket.sub, entries=tuple(bucket.entries)) for bucket in grouped.values()]
