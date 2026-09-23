"""家庭库业务：拉取共享库、diff 检测、渲染与轮询推送。基线存 gs_subscribe.extra_data。"""
from __future__ import annotations

import json
from typing import Any, Optional

from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe

from ..SteamConfig import SteamConfig
from ..utils.Api import (
    get_api_key,
    get_family_group_for_user,
    get_miniprofile,
    get_profile_items_equipped,
    get_shared_library_apps,
    get_user_Summaries,
    resolve_games_covers,
)
from ..utils.exceptions import SteamAPIError, SteamValidationError
from ..utils.helpers.profile import resolve_profile_assets
from ..utils.render import render_steam_wall
from ..utils.utils import steamid64_to_friend_code

FAMILY_TASK_NAME = "steam家庭库订阅"


def _parse_baseline(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _baseline_appids(baseline: dict) -> set[str]:
    raw = baseline.get("appids")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw}


def dump_family_baseline(
    family_groupid: str,
    family_name: str,
    appids: list[str],
    last_acquired_ts: int,
) -> str:
    return json.dumps(
        {
            "family_groupid": family_groupid,
            "family_name": family_name,
            "appids": appids,
            "last_acquired_ts": last_acquired_ts,
        },
        ensure_ascii=False,
    )


def _event_from_sub(sub: Any) -> Event:
    return Event(
        bot_id=sub.bot_id,
        user_id=sub.user_id,
        bot_self_id=sub.bot_self_id,
        user_type=sub.user_type,
        group_id=sub.group_id,
        real_bot_id=sub.bot_id,
        msg_id=sub.msg_id if sub.msg_id else "",
    )


async def _save_baseline_to_subs(
    subs: list,
    *,
    family_groupid: str,
    family_name: str,
    appids: list[str],
    last_acquired_ts: int,
) -> None:
    extra_data = dump_family_baseline(
        family_groupid, family_name, appids, last_acquired_ts
    )
    for sub in subs:
        try:
            await gs_subscribe.update_subscribe_data(
                subscribe_type="single",
                task_name=FAMILY_TASK_NAME,
                event=_event_from_sub(sub),
                extra_data=extra_data,
                uid=sub.uid,
            )
        except Exception as e:
            logger.warning(f"[SteamFamily] 更新订阅基线失败 user_id={sub.user_id}: {e!r}")


def normalize_family_apps(apps: list[dict], steamid64: str | None = None) -> list[dict]:
    """规范化家庭库条目：过滤不可用项，映射为游戏墙结构。"""
    result: list[dict] = []
    for app in apps:
        if not isinstance(app, dict):
            continue
        appid = app.get("appid")
        if not appid:
            continue
        exclude_reason = app.get("exclude_reason") or 0
        try:
            exclude_reason = int(exclude_reason)
        except Exception:
            exclude_reason = 0
        if exclude_reason != 0:
            continue
        playtime = app.get("rt_playtime") or 0
        try:
            playtime = int(playtime)
        except Exception:
            playtime = 0
        result.append(
            {
                "appid": appid,
                "name": app.get("name") or str(appid),
                "playtime_forever": playtime,
                "rt_time_acquired": int(app.get("rt_time_acquired") or 0),
                "owner_steamids": [str(x) for x in (app.get("owner_steamids") or [])],
            }
        )
    return result


def detect_new_family_apps(
    apps: list[dict],
    baseline_appids: set[str],
    last_acquired_ts: int,
) -> list[dict]:
    """检测家庭库新增：appid 集合差 + 入库时间戳，取并集。"""
    current_ids = {str(a.get("appid")) for a in apps if a.get("appid")}
    new_by_id = {aid for aid in current_ids if aid not in baseline_appids}
    new_by_ts = {
        str(a.get("appid"))
        for a in apps
        if a.get("appid") and int(a.get("rt_time_acquired") or 0) > last_acquired_ts
    }
    new_ids = new_by_id | new_by_ts
    return [a for a in apps if str(a.get("appid")) in new_ids]


async def fetch_family_library(steamid64: str) -> tuple[dict, list[dict]]:
    """拉取家庭组信息与共享库游戏列表。"""
    group = await get_family_group_for_user(steamid64)
    if not group:
        raise SteamValidationError(
            "未查询到 Steam 家庭组信息，请确认已完成 Steam 网页登录且账号已加入家庭"
        )
    family_groupid = group.get("family_groupid")
    if not family_groupid:
        raise SteamValidationError("该账号未加入 Steam 家庭组")

    family_name = ""
    family_group = group.get("family_group")
    if isinstance(family_group, dict):
        family_name = family_group.get("name") or ""
    family_name = family_name or str(family_groupid)

    apps_resp = await get_shared_library_apps(steamid64, str(family_groupid))
    if apps_resp is None:
        raise SteamAPIError("获取家庭库游戏列表失败，请稍后重试或重新登录 Steam")

    raw_apps = apps_resp.get("apps") or []
    if not isinstance(raw_apps, list):
        raw_apps = []
    apps = normalize_family_apps(raw_apps, steamid64)
    return {
        "family_groupid": str(family_groupid),
        "family_name": family_name,
    }, apps


async def build_family_wall_image(steamid64: str) -> bytes:
    """构建家庭库游戏墙图片。"""
    family_info, apps = await fetch_family_library(steamid64)
    if not apps:
        raise SteamValidationError("当前家庭库暂无可展示的游戏")

    user_data: dict[str, Any] = {
        "name": family_info.get("family_name") or "Steam家庭",
        "friend_code": steamid64_to_friend_code(steamid64),
        "avatar_url": "",
        "avatar_frame_url": None,
        "bg_url": None,
    }
    if get_api_key():
        try:
            players_res, miniprofile_data, items_data = await _gather_profile(steamid64)
            player = {}
            if isinstance(players_res, list) and players_res:
                player = players_res[0] or {}
            assets = await resolve_profile_assets(
                steamid64,
                player=player,
                miniprofile_data=miniprofile_data if isinstance(miniprofile_data, dict) else {},
                items_data=items_data if isinstance(items_data, dict) else {},
            )
            user_data["name"] = player.get("personaname") or user_data["name"]
            user_data["avatar_url"] = assets.avatar_url
            user_data["avatar_frame_url"] = assets.avatar_frame_url
            user_data["bg_url"] = assets.bg_url
        except Exception as e:
            logger.warning(f"[SteamFamily] 获取家庭墙用户资料失败 steamid={steamid64}: {e}")

    games_data = [
        {
            "appid": g.get("appid"),
            "name": g.get("name", ""),
            "playtime_forever": g.get("playtime_forever", 0),
        }
        for g in apps
    ]
    if SteamConfig.get_config("AllowGridDBCover").data:
        await resolve_games_covers(games_data)

    wall_title = f"家庭游戏墙 · {family_info.get('family_name')}"
    return await render_steam_wall(
        user_data,
        games_data,
        canvas_width=1200,
        min_playtime=0,
        wall_title=wall_title,
    )


async def _gather_profile(steamid64: str):
    import asyncio

    return await asyncio.gather(
        get_user_Summaries(steamid64),
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        return_exceptions=True,
    )


async def fetch_family_snapshot(steamid64: str) -> dict:
    """拉取家庭库并生成可写入 extra_data 的基线快照。"""
    family_info, apps = await fetch_family_library(steamid64)
    appids = [str(a.get("appid")) for a in apps if a.get("appid")]
    last_acquired = max((int(a.get("rt_time_acquired") or 0) for a in apps), default=0)
    return {
        "family_groupid": family_info["family_groupid"],
        "family_name": family_info["family_name"],
        "appids": appids,
        "last_acquired_ts": last_acquired,
        "apps": apps,
    }


async def poll_and_push_family_library() -> None:
    """家庭库轮询：用 gs_subscribe.extra_data 作基线做 diff 并推送。"""
    try:
        all_subs = await gs_subscribe.get_subscribe(task_name=FAMILY_TASK_NAME)
        if not all_subs:
            return

        subs_by_steamid: dict[str, list] = {}
        for sub in all_subs:
            sid = sub.uid
            if sid:
                subs_by_steamid.setdefault(sid, []).append(sub)

        for steamid64, subs in subs_by_steamid.items():
            try:
                snapshot = await fetch_family_snapshot(steamid64)
            except Exception as e:
                logger.warning(f"[SteamFamily] 轮询拉取家庭库失败 steamid={steamid64}: {e!r}")
                continue

            baseline: dict = {}
            for sub in subs:
                baseline = _parse_baseline(sub.extra_data)
                if baseline:
                    break

            apps = snapshot["apps"]
            current_ids = snapshot["appids"]
            current_ts = snapshot["last_acquired_ts"]

            if not baseline:
                await _save_baseline_to_subs(
                    subs,
                    family_groupid=snapshot["family_groupid"],
                    family_name=snapshot["family_name"],
                    appids=current_ids,
                    last_acquired_ts=current_ts,
                )
                continue

            new_apps = detect_new_family_apps(
                apps,
                _baseline_appids(baseline),
                int(baseline.get("last_acquired_ts") or 0),
            )

            await _save_baseline_to_subs(
                subs,
                family_groupid=snapshot["family_groupid"],
                family_name=snapshot["family_name"],
                appids=current_ids,
                last_acquired_ts=current_ts,
            )

            if not new_apps:
                continue

            lines = []
            for g in new_apps[:20]:
                owner_ids = g.get("owner_steamids") or []
                owner = owner_ids[-1] if owner_ids else ""
                from_str = f"来自 {owner}" if owner else ""
                lines.append(f"• {g.get('name')} ({g.get('appid')}) {from_str}".rstrip())
            more = ""
            if len(new_apps) > 20:
                more = f"\n...等共 {len(new_apps)} 款"

            push_text = (
                f"\n[Steam 家庭库订阅] 检测到家庭库新增游戏！\n"
                f"家庭：{snapshot.get('family_name')}\n"
                + "\n".join(lines)
                + more
            )
            for sub in subs:
                try:
                    await sub.send(
                        [
                            MessageSegment.at(sub.user_id),
                            MessageSegment.text(push_text),
                        ]
                    )
                except Exception as error:
                    logger.warning(
                        f"[SteamFamily] 推送家庭库失败 steamid={steamid64}, "
                        f"user_id={sub.user_id}: {error!r}"
                    )
    except Exception as error:
        logger.warning(f"[SteamFamily] 家庭库轮询失败: {error!r}")
