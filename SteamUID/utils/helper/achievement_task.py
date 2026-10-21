"""成就轮询任务的创建、删除与订阅开关判断。"""

from collections.abc import Sequence

from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from .notify import subscribe_task_name
from .status import ACHIEVEMENT_KIND
from ...steam_config import SteamConfig
from ..database.model_poll import SteamPoll

ACHIEVEMENT_TASK_NAME = "成就轮询"
_TASK_SEPARATOR = ":"


def achievement_task_key(steamid64: str, appid: str) -> str:
    return f"{steamid64}{_TASK_SEPARATOR}{appid}"


def parse_achievement_task_key(key: str) -> tuple[str, str] | None:
    steamid64, separator, appid = key.partition(_TASK_SEPARATOR)
    if not separator or not steamid64 or not appid:
        return None
    return steamid64, appid


async def achievement_push_enabled(steamid64: str) -> bool:
    """全局与个人订阅均开启时才追踪该账号的成就。"""
    if not SteamConfig.get_config("NotifySwitch").data:
        return False
    if ACHIEVEMENT_KIND not in SteamConfig.get_config("NotifyTypes").data:
        return False

    raw = await gs_subscribe.get_subscribe(subscribe_task_name(ACHIEVEMENT_KIND), uid=steamid64)
    if not isinstance(raw, Sequence):
        return False
    return any(isinstance(row, Subscribe) for row in raw)


async def ensure_achievement_task(steamid64: str, appid: str) -> bool:
    """按账号和游戏建立任务；已有任务时保留其成就基线。"""
    if not await achievement_push_enabled(steamid64):
        return False

    key = achievement_task_key(steamid64, appid)
    if await SteamPoll.get_row(ACHIEVEMENT_TASK_NAME, key) is None:
        await SteamPoll.upsert(ACHIEVEMENT_TASK_NAME, key, "")
    return True


async def delete_achievement_task(steamid64: str, appid: str) -> None:
    await SteamPoll.delete_row(ACHIEVEMENT_TASK_NAME, achievement_task_key(steamid64, appid))


async def prune_achievement_tasks(bound_steamids: set[str]) -> None:
    """清理解绑账号和格式非法的成就任务。"""
    rows = await SteamPoll.get_all(ACHIEVEMENT_TASK_NAME)
    for row in rows:
        parsed = parse_achievement_task_key(row.key)
        if parsed is not None and parsed[0] in bound_steamids:
            continue
        await SteamPoll.delete_row(ACHIEVEMENT_TASK_NAME, row.key)
