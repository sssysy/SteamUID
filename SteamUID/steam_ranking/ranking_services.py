"""四种排行卡片的数据聚合与出图：个人 / 群玩家 / 群游戏 / 群游戏玩家。"""

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence

from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.api.models import AppDetailsEntry
from ..utils.helper.bind import get_binds, session_ids
from ..utils.helper.game import resolve_game_ref
from ..utils.helper.config import region_cc, griddb_cover_key
from ..utils.helper.command import resolve_viewer
from ..utils.helper.profile import load_profile_assets
from ..utils.helper.ranking import load_group_members
from ..utils.helper.steamid import auto2steamid64
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.game_detail import load_store_detail
from ..utils.database.model_bind import SteamBind
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.game_ranking import GameRankingEntry, render_game_ranking
from ..utils.render.html.user_ranking import (
    RankingBadge,
    UserRankingEntry,
    render_user_ranking,
)
from ..utils.render.html.static_assets import get_img_cache_url, get_default_avatar_url
from ..utils.database.model_play_record import SteamPlayRecord

_TAG = "[Steam·排行]"
_DEFAULT_LIMIT = 10


def _record_seconds(record: SteamPlayRecord) -> int:
    """单条游玩会话的秒数；未结束或时间倒挂视为 0。"""
    end_ts = record.end_ts
    if end_ts is None or end_ts <= record.start_ts:
        return 0
    return end_ts - record.start_ts


def _limit_of(words: Sequence[str]) -> int:
    """首个参数为条数时取其值，否则回落默认 10。"""
    if words and words[0].isdigit() and int(words[0]) > 0:
        return int(words[0])
    return _DEFAULT_LIMIT


def _detail_name(detail: AppDetailsEntry | None) -> str:
    """商店详情里的游戏名；缺失返回空串。"""
    if detail is None or "data" not in detail or "name" not in detail["data"]:
        return ""
    return detail["data"]["name"]


def _steamid_user_map(binds: Sequence[SteamBind]) -> dict[str, str]:
    """steamid64 到绑定用户 ID 的映射；同账号被多人绑定时取其一。"""
    mapping: dict[str, str] = {}
    for bind in binds:
        mapping[bind.steamid64] = bind.user_id
    return mapping


def _user_totals(records: Sequence[SteamPlayRecord], steamid_to_user: Mapping[str, str]) -> dict[str, int]:
    """按用户累加游玩秒数；不在绑定表内的记录跳过。"""
    totals: defaultdict[str, int] = defaultdict(int)
    for record in records:
        if record.steamid64 not in steamid_to_user:
            continue
        seconds = _record_seconds(record)
        if seconds <= 0:
            continue
        totals[steamid_to_user[record.steamid64]] += seconds
    return dict(totals)


def _app_totals(records: Sequence[SteamPlayRecord]) -> dict[str, int]:
    """按游戏累加游玩秒数。"""
    totals: defaultdict[str, int] = defaultdict(int)
    for record in records:
        seconds = _record_seconds(record)
        if seconds <= 0:
            continue
        totals[record.appid] += seconds
    return dict(totals)


def _rank_desc(totals: Mapping[str, int], limit: int) -> list[tuple[str, int]]:
    """按秒数降序取前 limit 项。"""
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return ranked[:limit]


async def _game_entries(seconds: Mapping[str, int]) -> list[GameRankingEntry]:
    """按传入映射顺序批量解析游戏名与封面，组装成排行行。"""
    appids = list(seconds)
    country = region_cc()
    griddb_key = griddb_cover_key()
    covers, details = await asyncio.gather(
        resolve_cover_names(appids, country=country, griddb_key=griddb_key),
        asyncio.gather(*(load_store_detail(appid, country) for appid in appids)),
    )

    return [
        GameRankingEntry(
            appid=appid,
            name=_detail_name(detail) or appid,
            cover_url=get_img_cache_url(covers[appid]) if appid in covers else "",
            duration_seconds=seconds[appid],
        )
        for appid, detail in zip(appids, details)
    ]


async def _game_badge(appid: str, fallback_name: str) -> RankingBadge:
    """游戏徽标：名称优先商店详情，图标取封面首图。"""
    country = region_cc()
    griddb_key = griddb_cover_key()
    detail, covers = await asyncio.gather(
        load_store_detail(appid, country),
        resolve_cover_names([appid], country=country, griddb_key=griddb_key),
    )
    return RankingBadge(
        name=_detail_name(detail) or fallback_name,
        logo_url=get_img_cache_url(covers[appid]) if appid in covers else "",
    )


async def _account_pill(steamid64: str) -> PillAccount | None:
    """右上角账号胶囊；资料抓取失败时跳过胶囊，不影响排行本体。"""
    loaded = await asyncio.gather(load_profile_assets(steamid64), return_exceptions=True)
    profile = loaded[0]
    if isinstance(profile, BaseException):
        logger.warning(f"{_TAG} 胶囊资料获取失败 {steamid64}: {profile!r}")
        return None
    return PillAccount(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=get_img_cache_url(profile.background_name),
    )


async def _user_entries(group_id: str, ranked: Sequence[tuple[str, int]]) -> list[UserRankingEntry]:
    """把 (user_id, 秒数) 排行补齐群名片与头像后组装成排行行。"""
    members = await load_group_members(group_id, [user_id for user_id, _ in ranked])
    return [
        UserRankingEntry(
            name=members[user_id].name,
            avatar_url=(get_img_cache_url(members[user_id].avatar_name) or get_default_avatar_url()),
            duration_seconds=seconds,
        )
        for user_id, seconds in ranked
    ]


async def _group_binds(ev: Event) -> tuple[str, list[SteamBind]]:
    """当前群号与该群全部绑定；私聊直接报错。"""
    if not ev.group_id:
        raise ValueError("请在群聊中使用此功能")
    bot_id, bot_self_id, group_id = session_ids(ev)
    binds = await SteamBind.get_binds_by_group(bot_id, bot_self_id, group_id)
    return group_id, binds


async def build_group_player_ranking(ev: Event) -> bytes:
    """steam群玩家排行[条数]：按群内用户累计游玩时长降序出图。"""
    group_id, binds = await _group_binds(ev)
    if not binds:
        raise ValueError("本群暂无游戏时长排行数据")

    steamid_to_user = _steamid_user_map(binds)
    records = await SteamPlayRecord.get_records_by_steamids(list(steamid_to_user))
    totals = _user_totals(records, steamid_to_user)
    if not totals:
        raise ValueError("本群暂无游戏时长排行数据")

    ranked = _rank_desc(totals, _limit_of(ev.text.split()))
    entries = await _user_entries(group_id, ranked)
    return await render_user_ranking(f"steam群游玩时长排行 Top{len(entries)}", entries)


async def build_group_game_ranking(ev: Event) -> bytes:
    """steam群游戏排行[条数]：按群内所有游戏累计时长降序出图。"""
    _, binds = await _group_binds(ev)
    if not binds:
        raise ValueError("本群暂无游戏时长排行数据")

    steamids = list(dict.fromkeys(bind.steamid64 for bind in binds))
    records = await SteamPlayRecord.get_records_by_steamids(steamids)
    totals = _app_totals(records)
    if not totals:
        raise ValueError("本群暂无游戏时长排行数据")

    ranked = dict(_rank_desc(totals, _limit_of(ev.text.split())))
    entries = await _game_entries(ranked)
    return await render_game_ranking(f"steam群游戏排行 Top{len(entries)}", entries)


async def build_group_game_player_ranking(ev: Event) -> bytes:
    """steam群游戏玩家排行<游戏名/AppID> [条数]：按该游戏群内玩家时长降序出图。"""
    group_id, binds = await _group_binds(ev)

    words = ev.text.split()
    if not words:
        raise ValueError("请输入游戏名或 AppID，例如：steam群游戏玩家排行 730")
    ref = await resolve_game_ref(words[0], cc=region_cc())

    if not binds:
        raise ValueError(f"未找到 {ref.appid} 的相关游玩数据！")

    steamid_to_user = _steamid_user_map(binds)
    records = await SteamPlayRecord.get_records_by_steamids(list(steamid_to_user))
    totals = _user_totals([record for record in records if record.appid == ref.appid], steamid_to_user)
    if not totals:
        raise ValueError(f"未找到 {ref.appid} 的相关游玩数据！")

    ranked = _rank_desc(totals, _limit_of(words[1:]))
    entries = await _user_entries(group_id, ranked)
    badge = await _game_badge(ref.appid, ref.name)
    return await render_user_ranking(f"steam群游戏玩家排行 Top{len(entries)}", entries, badge=badge)


async def build_self_ranking(ev: Event, *, allow_at: bool) -> bytes:
    """steam排行[steamid/好友码] [条数]：目标在本群的游戏时长排行。"""
    if not ev.group_id:
        raise ValueError("请在群聊中使用此功能")

    words = ev.text.split()
    target_user_id = resolve_viewer(ev, allow_at=allow_at)

    steamid64: str | None = None
    if ev.at:
        limit = _limit_of(words)
    else:
        steamid64 = auto2steamid64(words[0]) if words else None
        limit = _limit_of(words[1:] if steamid64 is not None else words)

    is_self = steamid64 is None and target_user_id == ev.user_id
    if steamid64 is not None:
        target_steamids = [steamid64]
    else:
        binds = await get_binds(ev, target_user_id)
        if not binds:
            raise ValueError("您在当前群未绑定 Steam 账号，请先绑定" if is_self else "对方在当前群未绑定 Steam 账号")
        target_steamids = list(dict.fromkeys(bind.steamid64 for bind in binds))

    records = await SteamPlayRecord.get_records_by_steamids(target_steamids)
    totals = _app_totals(records)
    if not totals:
        raise ValueError("您在当前群暂无游戏时长数据" if is_self else "对方在当前群暂无游戏时长数据")

    ranked = dict(_rank_desc(totals, limit))
    entries = await _game_entries(ranked)
    account = await _account_pill(target_steamids[0])
    return await render_game_ranking(f"steam个人排行 Top{len(entries)}", entries, account)
