"""成就轮询：对进行中的游玩会话比对成就、刷新基线并通知。"""

import time
from dataclasses import dataclass, replace
from collections.abc import Sequence

import httpx
from gsuid_core.logger import logger

from ..steam_config import (
    get_api_keys,
    get_key_cooldown,
    get_notify_switch,
    get_push_options,
)
from ..utils.database.model_bind import SteamBind
from ..utils.database.model_play_record import SteamPlayRecord
from ..utils.database.model_poll import SteamPoll
from ..utils.render.push import dispatch_events
from ..utils.helper.status import (
    AchievementUnlock,
    UserStatusEvent,
    diff_achievements,
    names_from_json,
    names_to_json,
    unlocked_names,
)
from ..utils.api.models import PlayerAchievement
from ..utils.helper.steam_api import (
    fetch_achievement_schema,
    fetch_player_achievements,
    fetch_player_summaries,
)

_TAG = "[Steam·成就轮询]"
TASK_NAME = "成就轮询"


def _baseline_key(steamid64: str, appid: str) -> str:
    return f"{steamid64}:{appid}"


async def _load_baselines() -> dict[tuple[str, str], list[str]]:
    """一次取回全部成就基线，键为 (steamid64, appid)。"""
    rows = await SteamPoll.get_all(TASK_NAME)
    baselines: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        steamid64, _, appid = row.key.partition(":")
        if not steamid64 or not appid:
            continue
        baselines[(steamid64, appid)] = names_from_json(row.value)
    return baselines


async def _save_baseline(steamid64: str, appid: str, names: list[str]) -> None:
    await SteamPoll.upsert(
        TASK_NAME, _baseline_key(steamid64, appid), names_to_json(names)
    )


async def _prune_baselines(
    alive: set[tuple[str, str]], baselines: dict[tuple[str, str], list[str]]
) -> None:
    """清掉已结束会话的成就基线。"""
    for steamid64, appid in baselines:
        if (steamid64, appid) not in alive:
            await SteamPoll.delete_row(TASK_NAME, _baseline_key(steamid64, appid))


@dataclass(frozen=True)
class _PlayerInfo:
    """推送文案与卡片需要的玩家信息。"""

    nickname: str
    title: str
    avatar: str


async def _load_players(
    steamids: Sequence[str], *, keys: Sequence[str], cooldown: int
) -> dict[str, _PlayerInfo]:
    """返回在玩账号的 steamid 到玩家信息映射。"""
    players = await fetch_player_summaries(steamids, keys=keys, cooldown=cooldown)
    infos: dict[str, _PlayerInfo] = {}
    for player in players:
        if "steamid" not in player:
            continue
        infos[player["steamid"]] = _PlayerInfo(
            nickname=player["personaname"] if "personaname" in player else "",
            title=player["gameextrainfo"] if "gameextrainfo" in player else "",
            avatar=player["avatarfull"] if "avatarfull" in player else "",
        )
    return infos


async def _load_unlocks(
    appid: str, *, keys: Sequence[str], cooldown: int
) -> dict[str, AchievementUnlock]:
    """apiname 到成就定义的映射，缺项由调用方回落 apiname。"""
    entries = await fetch_achievement_schema(appid, keys=keys, cooldown=cooldown)
    unlocks: dict[str, AchievementUnlock] = {}
    for entry in entries:
        if "name" not in entry:
            continue
        unlocks[entry["name"]] = AchievementUnlock(
            name=entry["displayName"] if "displayName" in entry else entry["name"],
            description=entry["description"] if "description" in entry else "",
            icon=entry["icon"] if "icon" in entry else "",
        )
    return unlocks


def _unlock_times(entries: list[PlayerAchievement]) -> dict[str, int]:
    """apiname 到解锁时间戳的映射，缺项由调用方回落本轮轮询时间。"""
    times: dict[str, int] = {}
    for entry in entries:
        if "apiname" in entry and "unlocktime" in entry:
            times[entry["apiname"]] = entry["unlocktime"]
    return times


async def _poll_once() -> None:
    # 成就只为推送存在，总开关关闭时整轮跳过
    if not get_notify_switch():
        return

    baselines = await _load_baselines()
    records = await SteamPlayRecord.get_open_records()
    # 只跟进仍有绑定的账号，解绑后的残留会话不再消耗接口
    bound = set(await SteamBind.get_all_steamids())
    records = [record for record in records if record.steamid64 in bound]
    alive = {(record.steamid64, record.appid) for record in records}
    await _prune_baselines(alive, baselines)
    if not records:
        return

    keys = get_api_keys()
    if not keys:
        logger.warning(f"{_TAG} 未配置 Steam API Key，跳过本轮轮询")
        return
    cooldown = get_key_cooldown()

    steamids = sorted({record.steamid64 for record in records})
    infos = await _load_players(steamids, keys=keys, cooldown=cooldown)

    now = int(time.time())
    schema_cache: dict[str, dict[str, AchievementUnlock]] = {}
    events: list[UserStatusEvent] = []

    for record in records:
        pair = (record.steamid64, record.appid)

        payload = await fetch_player_achievements(
            record.appid, record.steamid64, keys=keys, cooldown=cooldown
        )
        if "success" in payload and not payload["success"]:
            continue
        entries = payload["achievements"] if "achievements" in payload else []

        previous = baselines[pair] if pair in baselines else None
        unlocked = unlocked_names(entries)
        if previous is None or set(previous) != set(unlocked):
            await _save_baseline(record.steamid64, record.appid, unlocked)
        if previous is None:
            continue

        fresh = diff_achievements(set(previous), entries)
        if not fresh:
            continue

        if record.appid not in schema_cache:
            schema_cache[record.appid] = await _load_unlocks(
                record.appid, keys=keys, cooldown=cooldown
            )
        unlocks = schema_cache[record.appid]
        info = infos[record.steamid64] if record.steamid64 in infos else _PlayerInfo("", "", "")
        title = info.title or (payload["gameName"] if "gameName" in payload else "")
        times = _unlock_times(entries)
        for apiname in fresh:
            unlock = unlocks[apiname] if apiname in unlocks else AchievementUnlock(name=apiname)
            unlocked_at = times[apiname] if apiname in times else now
            events.append(
                UserStatusEvent(
                    kind="获得成就",
                    steamid64=record.steamid64,
                    ts=now,
                    nickname=info.nickname,
                    appid=record.appid,
                    game_name=title,
                    avatar=info.avatar,
                    achievement=replace(unlock, time=unlocked_at),
                )
            )

    await dispatch_events(events, options=get_push_options())


async def poll_achievements_once() -> None:
    """单轮成就轮询；异常在此收口，避免打断调度器。"""
    try:
        await _poll_once()
    except httpx.HTTPStatusError as error:
        logger.warning(f"{_TAG} 接口请求失败: HTTP {error.response.status_code}")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 网络请求失败: {type(error).__name__}")
    except Exception as error:
        logger.exception(f"{_TAG} 轮询异常: {type(error).__name__}")
