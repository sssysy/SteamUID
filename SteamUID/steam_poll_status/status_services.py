"""用户状态轮询：拉取摘要、比对、落库与通知的编排。"""

import time
from collections.abc import Sequence

import httpx

from gsuid_core.logger import logger

from ..steam_config import SteamConfig
from ..utils.key_pool import has_available_api_key
from ..utils.render.push import dispatch_events
from ..utils.helper.config import push_options
from ..utils.helper.status import (
    StatusSnapshot,
    UserStatusEvent,
    diff_status,
    to_snapshot,
    snapshot_to_json,
    snapshot_from_json,
)
from ..utils.helper.steam_api import fetch_player_summaries
from ..utils.database.model_bind import SteamBind
from ..utils.database.model_poll import SteamPoll
from ..utils.helper.achievement_task import (
    delete_achievement_task,
    ensure_achievement_task,
    prune_achievement_tasks,
)
from ..utils.database.model_play_record import SteamPlayRecord

_TAG = "[Steam·状态轮询]"
TASK_NAME = "用户状态轮询"
_BASELINE_PREFIX = "status:"
# 启动或重载后首次观测到的账号只更新基线，不补推停机期间变化
_startup_pending: set[str] | None = None


def _baseline_key(steamid64: str) -> str:
    return f"{_BASELINE_PREFIX}{steamid64}"


async def _load_baselines() -> dict[str, StatusSnapshot]:
    """一次取回全部基线；任务名下只认 status: 前缀的行。"""
    rows = await SteamPoll.get_all(TASK_NAME)
    baselines: dict[str, StatusSnapshot] = {}
    for row in rows:
        if not row.key.startswith(_BASELINE_PREFIX):
            continue
        baselines[row.key[len(_BASELINE_PREFIX) :]] = snapshot_from_json(row.value)
    return baselines


async def _save_baselines(changed: dict[str, StatusSnapshot]) -> None:
    for steamid64, snapshot in changed.items():
        await SteamPoll.upsert(TASK_NAME, _baseline_key(steamid64), snapshot_to_json(snapshot))


async def _prune_baselines(steamids: set[str], baselines: dict[str, StatusSnapshot]) -> None:
    """清理解绑账号的基线，避免表随历史绑定无限增长。"""
    for steamid64 in baselines:
        if steamid64 not in steamids:
            await SteamPoll.delete_row(TASK_NAME, _baseline_key(steamid64))


async def _record_play_sessions(
    events: Sequence[UserStatusEvent],
    seeds: Sequence[tuple[str, str]],
    now: int,
) -> None:
    """按事件维护游玩会话；结束先于开始写入，切换游戏时区间不重叠。

    seeds 是首次见到就已在游戏的账号，补一条开始记录，避免后续结束事件落空。
    """
    for steamid64, appid in seeds:
        await SteamPlayRecord.start_record(steamid64, appid, now)
        await ensure_achievement_task(steamid64, appid)
    for event in events:
        if event.kind == "开始游戏":
            await SteamPlayRecord.start_record(event.steamid64, event.appid, now)
            await ensure_achievement_task(event.steamid64, event.appid)
        elif event.kind == "结束游戏":
            await SteamPlayRecord.end_record(event.steamid64, event.appid, now)
            await delete_achievement_task(event.steamid64, event.appid)


async def _poll_once() -> None:
    global _startup_pending

    keys = SteamConfig.get_config("SteamAPIKey").data
    if not has_available_api_key(keys):
        return

    baselines = await _load_baselines()
    steamids = await SteamBind.get_all_steamids()
    bound = set(steamids)
    await _prune_baselines(bound, baselines)
    await prune_achievement_tasks(bound)
    if _startup_pending is None:
        _startup_pending = set(steamids)
    else:
        _startup_pending.intersection_update(steamids)
    if not steamids:
        return
    pending = _startup_pending

    players = await fetch_player_summaries(steamids, keys=keys, cooldown=SteamConfig.get_config("KeyPoolCooldown").data)

    now = int(time.time())

    events: list[UserStatusEvent] = []
    current: dict[str, StatusSnapshot] = {}
    for player in players:
        if "steamid" not in player:
            continue
        steamid64 = player["steamid"]
        snapshot = to_snapshot(player)
        previous = baselines[steamid64] if steamid64 in baselines else None
        events.extend(diff_status(steamid64, previous, snapshot, now))
        current[steamid64] = snapshot

    changed: dict[str, StatusSnapshot] = {}
    for steamid64, snapshot in current.items():
        if steamid64 not in baselines or baselines[steamid64] != snapshot:
            changed[steamid64] = snapshot
    await _save_baselines(changed)
    silent_steamids = pending.intersection(current)
    startup_games: list[tuple[str, str]] = []
    for steamid64 in silent_steamids:
        snapshot = current[steamid64]
        gameid = snapshot["gameid"] if "gameid" in snapshot else ""
        if gameid and steamid64 in baselines:
            startup_games.append((steamid64, gameid))
    pending.difference_update(current)

    seeds: list[tuple[str, str]] = []
    for steamid64, snapshot in current.items():
        if steamid64 in baselines:
            continue
        gameid = snapshot["gameid"] if "gameid" in snapshot else ""
        if gameid:
            seeds.append((steamid64, gameid))

    for steamid64, appid in startup_games:
        await ensure_achievement_task(steamid64, appid)
    await _record_play_sessions(events, seeds, now)

    notify_events = [event for event in events if event.steamid64 not in silent_steamids]
    if notify_events and SteamConfig.get_config("NotifySwitch").data:
        await dispatch_events(notify_events, options=push_options())


async def poll_status_once() -> None:
    """单轮用户状态轮询；异常在此收口，避免打断调度器。"""
    try:
        await _poll_once()
    except httpx.HTTPStatusError as error:
        logger.warning(f"{_TAG} 接口请求失败: HTTP {error.response.status_code}")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 网络请求失败: {type(error).__name__}")
    except Exception as error:
        logger.exception(f"{_TAG} 轮询异常: {type(error).__name__}")
