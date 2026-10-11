"""成就查询与轮询：查询命令出图，轮询对进行中的游玩会话比对成就并通知。"""

import time
import asyncio
from dataclasses import replace, dataclass
from collections.abc import Sequence

import httpx

from gsuid_core.logger import logger

from ..steam_config import (
    get_api_keys,
    get_region_cc,
    get_griddb_key,
    get_key_cooldown,
    get_push_options,
    get_notify_switch,
    get_allow_griddb_cover,
)
from ..utils.api.cover import build_app_icon_url, get_official_cover_url
from ..utils.api.models import PlayerAchievement, AchievementSchemaEntry
from ..utils.downloader import download
from ..utils.helper.game import resolve_game_ref
from ..utils.render.push import dispatch_events
from ..utils.helper.status import (
    UserStatusEvent,
    AchievementUnlock,
    names_to_json,
    unlocked_names,
    names_from_json,
    diff_achievements,
)
from ..utils.helper.profile import load_profile_assets
from ..utils.helper.steam_api import (
    fetch_owned_games,
    fetch_player_summaries,
    fetch_achievement_schema,
    fetch_player_achievements,
)
from ..utils.helper.game_cover import resolve_cover_name
from ..utils.helper.game_detail import load_store_detail
from ..utils.database.model_bind import SteamBind
from ..utils.database.model_poll import SteamPoll
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.static_assets import get_img_cache_url, get_default_avatar_url
from ..utils.database.model_play_record import SteamPlayRecord
from ..utils.render.html.achievement_card import (
    AchievementCard,
    AchievementSlot,
    displayed_slots,
    render_achievement_card,
)

_TAG = "[Steam·成就轮询]"
_QUERY_TAG = "[Steam·游戏成就]"
# 未精确命中本体游戏时的提示，由命令层在出图前发给用户
_FALLBACK_HINT = "未精确匹配到本体游戏，已使用最接近的结果 {name}({appid})，如有错误请使用 appid 精确匹配游戏"
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
    await SteamPoll.upsert(TASK_NAME, _baseline_key(steamid64, appid), names_to_json(names))


async def _prune_baselines(alive: set[tuple[str, str]], baselines: dict[tuple[str, str], list[str]]) -> None:
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


async def _load_players(steamids: Sequence[str], *, keys: Sequence[str], cooldown: int) -> dict[str, _PlayerInfo]:
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


async def _load_unlocks(appid: str, *, keys: Sequence[str], cooldown: int) -> dict[str, AchievementUnlock]:
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
    events: list[UserStatusEvent] = []

    for record in records:
        pair = (record.steamid64, record.appid)

        payload = await fetch_player_achievements(record.appid, record.steamid64, keys=keys, cooldown=cooldown)
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

        unlocks = await _load_unlocks(record.appid, keys=keys, cooldown=cooldown)
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


@dataclass(frozen=True)
class AchievementCardResult:
    """出图结果：图片字节，以及非致命提示（无提示时为空串）。"""

    image: bytes
    hint: str


async def _owned_icon_url(steamid64: str, appid: str, *, keys: Sequence[str], cooldown: int) -> str:
    """库内这款游戏的客户端小图标直链；库接口失败或未收录时回落官方小胶囊图。"""
    try:
        payload = await fetch_owned_games(steamid64, keys=keys, cooldown=cooldown)
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_QUERY_TAG} 游戏库查询失败，回落官方图标: {type(error).__name__}")
        return get_official_cover_url(appid, "capsule_sm_120")

    games = payload["games"] if "games" in payload else []
    for game in games:
        if "appid" not in game or str(game["appid"]) != appid:
            continue
        if "img_icon_url" in game and game["img_icon_url"]:
            return build_app_icon_url(appid, game["img_icon_url"])
        break
    return get_official_cover_url(appid, "capsule_sm_120")


def _achievement_slots(
    entries: Sequence[PlayerAchievement], schema: Sequence[AchievementSchemaEntry]
) -> list[AchievementSlot]:
    """合并玩家进度与成就定义：已解锁在前按解锁时间倒序，未解锁保持原序。"""
    definitions: dict[str, AchievementSchemaEntry] = {}
    for entry in schema:
        if "name" in entry:
            definitions[entry["name"]] = entry

    unlocked: list[AchievementSlot] = []
    locked: list[AchievementSlot] = []
    for entry in entries:
        apiname = entry["apiname"] if "apiname" in entry else ""
        definition = definitions[apiname] if apiname in definitions else None
        achieved = entry["achieved"] == 1 if "achieved" in entry else False

        name = apiname
        description = ""
        icon = ""
        if definition is not None:
            name = definition["displayName"] if "displayName" in definition else apiname
            description = definition["description"] if "description" in definition else ""
            if achieved:
                icon = definition["icon"] if "icon" in definition else ""
            else:
                icon = definition["icongray"] if "icongray" in definition else ""
                if not icon:
                    icon = definition["icon"] if "icon" in definition else ""
        if "name" in entry and entry["name"]:
            name = entry["name"]
        if "description" in entry and entry["description"]:
            description = entry["description"]

        unlocktime = entry["unlocktime"] if "unlocktime" in entry else 0
        slot = AchievementSlot(
            name=name or apiname,
            description=description,
            icon_url=icon,
            achieved=achieved,
            unlocked_at=unlocktime if achieved else 0,
        )
        if achieved:
            unlocked.append(slot)
        else:
            locked.append(slot)

    unlocked.sort(key=lambda slot: slot.unlocked_at, reverse=True)
    return unlocked + locked


async def _image_links(urls: Sequence[str]) -> dict[str, str]:
    """远程图落 img_cache 后换成挂载直链；失败项不进表，由渲染层回落默认图。"""
    ordered = sorted({url for url in urls if url})
    if not ordered:
        return {}

    results = await asyncio.gather(*(download(url, kind="image") for url in ordered), return_exceptions=True)
    links: dict[str, str] = {}
    failed = 0
    for url, result in zip(ordered, results):
        if isinstance(result, BaseException) or result is None:
            failed += 1
            continue
        link = get_img_cache_url(result.name)
        if link:
            links[url] = link
    if failed:
        logger.warning(f"{_QUERY_TAG} {failed} 张图片下载失败，将回落默认图标")
    return links


async def build_achievement_card(steamid64: str, query: str) -> AchievementCardResult:
    """出图入口：解析游戏 -> 拉成就与素材 -> 组装 -> 渲染。"""
    keys = get_api_keys()
    if not keys:
        raise ValueError("请先配置 Steam API Key")
    cooldown = get_key_cooldown()

    ref = await resolve_game_ref(query, cc=get_region_cc())
    payload = await fetch_player_achievements(ref.appid, steamid64, keys=keys, cooldown=cooldown)
    if "success" in payload and not payload["success"]:
        raise ValueError("未获取到成就数据，可能该游戏无成就、steam 资料未公开或登录授权已失效")
    entries = payload["achievements"] if "achievements" in payload else []
    if not entries:
        raise ValueError("该游戏暂无成就数据")

    griddb_key = get_griddb_key() if get_allow_griddb_cover() else ""
    schema, detail, profile, cover_name, icon_raw = await asyncio.gather(
        fetch_achievement_schema(ref.appid, keys=keys, cooldown=cooldown),
        load_store_detail(ref.appid, None),
        load_profile_assets(steamid64),
        resolve_cover_name(ref.appid, country=get_region_cc(), griddb_key=griddb_key),
        _owned_icon_url(steamid64, ref.appid, keys=keys, cooldown=cooldown),
    )

    slots = _achievement_slots(entries, schema)
    links = await _image_links([icon_raw] + [slot.icon_url for slot in displayed_slots(slots)])
    achievements = tuple(
        replace(slot, icon_url=links[slot.icon_url] if slot.icon_url in links else "") for slot in slots
    )

    # 游戏名优先取商店详情，其次玩家成就接口返回的游戏名
    game_name = payload["gameName"] if "gameName" in payload and payload["gameName"] else ref.name
    store_name = ""
    if detail is not None and "data" in detail and "name" in detail["data"]:
        store_name = detail["data"]["name"]
    if store_name:
        game_name = store_name

    card = AchievementCard(
        game_name=game_name,
        game_icon_url=links[icon_raw] if icon_raw in links else "",
        cover_url=get_img_cache_url(cover_name),
        account=PillAccount(
            name=profile.name,
            friend_code=profile.friend_code,
            avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
            frame_url=get_img_cache_url(profile.frame_name),
            background_url=get_img_cache_url(profile.background_name),
        ),
        achievements=achievements,
    )
    hint = "" if ref.exact else _FALLBACK_HINT.format(name=game_name, appid=ref.appid)
    return AchievementCardResult(image=await render_achievement_card(card), hint=hint)
