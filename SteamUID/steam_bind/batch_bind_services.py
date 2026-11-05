"""批量绑定：解析用户与 Steam 账号对，并跳过会话内已存在的绑定。"""

import re
from dataclasses import dataclass
from collections.abc import Sequence

from gsuid_core.models import Event

from ..steam_config import SteamConfig
from ..utils.helper.bind import add_bind, get_binds, session_ids
from ..utils.helper.steamid import auto2steamid64
from ..utils.database.model_bind import SteamBind

_ADMIN_PM = 3
_SEPARATOR_RE = re.compile(r"[,，]")
_SLASH_RE = re.compile(r"[/\\]")
_USAGE = (
    '命令格式错误，请用"/"分割用户id和steamid，并用","分割不同用户\n'
    "比如：steam批量绑定12345678/7656xxxx,23456789/7656xxxxxx"
)


@dataclass(frozen=True)
class BatchBindTarget:
    """一条待写入的绑定。"""

    user_id: str
    steamid64: str


@dataclass(frozen=True)
class BatchBindResult:
    """批量绑定结果：成功数与被跳过的冲突用户。"""

    bound: int
    conflicts: tuple[str, ...]


def ensure_admin(ev: Event) -> None:
    """命令内补充校验，复用绑定 SV 时仍限制管理员及以上。"""
    if ev.user_pm > _ADMIN_PM:
        raise ValueError("该命令仅限管理员及以上使用")


def parse_batch_bind(raw: str) -> list[BatchBindTarget]:
    """按逗号拆用户项、按斜杠拆用户与账号；任一格式错误整批拒绝。"""
    text = raw.strip()
    if not text:
        raise ValueError(_USAGE)

    targets: list[BatchBindTarget] = []
    for item in _SEPARATOR_RE.split(text):
        parts = _SLASH_RE.split(item.strip())
        if len(parts) != 2:
            raise ValueError(_USAGE)
        user_id = parts[0].strip()
        steamid64 = auto2steamid64(parts[1].strip())
        if not user_id or steamid64 is None:
            raise ValueError(_USAGE)
        targets.append(BatchBindTarget(user_id=user_id, steamid64=steamid64))
    return targets


async def batch_bind_accounts(ev: Event, targets: Sequence[BatchBindTarget]) -> BatchBindResult:
    """逐项写入绑定并建立默认订阅；已存在的绑定跳过并记录冲突用户。"""
    defaults = SteamConfig.get_config("DefaultNotifyTypes").data
    bot_id, bot_self_id, group_id = session_ids(ev)
    existing_by_user: dict[str, set[str]] = {}
    owner_by_steamid: dict[str, str] = {}
    if group_id:
        for bind in await SteamBind.get_binds_by_group(bot_id, bot_self_id, group_id):
            owner_by_steamid[bind.steamid64] = bind.user_id

    bound = 0
    conflicts: list[str] = []
    for target in targets:
        if target.user_id not in existing_by_user:
            existing_by_user[target.user_id] = {bind.steamid64 for bind in await get_binds(ev, target.user_id)}
        already_bound = target.steamid64 in existing_by_user[target.user_id]
        owner = owner_by_steamid[target.steamid64] if target.steamid64 in owner_by_steamid else None
        if already_bound or (owner is not None and owner != target.user_id):
            conflicts.append(target.user_id)
            continue

        await add_bind(ev, target.user_id, target.steamid64, defaults)
        existing_by_user[target.user_id].add(target.steamid64)
        if group_id:
            owner_by_steamid[target.steamid64] = target.user_id
        bound += 1
    return BatchBindResult(bound=bound, conflicts=tuple(conflicts))
