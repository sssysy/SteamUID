"""游戏价格轮询：统一处理降价 / 史低订阅、基线、史低缓存与推送。"""

import time
from datetime import datetime, timezone
from dataclasses import dataclass
from collections.abc import Sequence

import httpx
import msgspec

from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..steam_config import SteamConfig
from ..utils.helper.price import price_overview, fetch_price_overviews
from ..utils.api.augmented import fetch_store_lows
from ..utils.helper.config import region_cc, region_lang, griddb_cover_key
from ..utils.helper.game_cover import resolve_cover_name
from ..utils.helper.price_drop import (
    BASELINE_TASK,
    SUBSCRIBE_TASK,
    PriceMode,
    PriceBaseline,
    is_drop,
    price_text,
    to_baseline,
    appid_of_key,
    baseline_key,
    discount_label,
    baseline_to_json,
    subscription_mode,
    baseline_from_json,
)
from ..utils.helper.game_detail import (
    pics_game_name,
    clean_description,
    load_store_detail,
    store_detail_name,
)
from ..utils.helper.history_low import (
    HISTORY_LOW_CACHE_TYPE,
    HistoryLowCache,
    history_low_key,
    history_low_to_json,
    missing_history_low,
    history_low_from_game,
    history_low_from_json,
    needs_history_low_refresh,
)
from ..utils.database.model_poll import SteamPoll
from ..utils.database.model_cache import SteamCache
from ..utils.render.html.price_drop import PriceDropCard, render_price_drop_card
from ..utils.render.html.static_assets import get_img_cache_url

_TAG = "[Steam·降价轮询]"
_NO_DESC = "暂无游戏简介"
# 启动或重载后首次观测到的订阅只更新状态，不补推停机期间变化
_startup_pending: set[str] | None = None


@dataclass(frozen=True)
class _Drop:
    """一次待推送的价格事件：appid + 旧基线 + 新基线。"""

    appid: str
    previous: PriceBaseline
    current: PriceBaseline


def _subscribe_rows(rows: object) -> list[Subscribe]:
    """框架订阅接口无类型标注，这里立刻收窄为 Subscribe。"""
    if not isinstance(rows, Sequence):
        return []
    return [row for row in rows if isinstance(row, Subscribe)]


def _subscribers_by_appid(rows: Sequence[Subscribe]) -> dict[str, list[Subscribe]]:
    """按 appid 聚合订阅行，推送时逐个会话发送。"""
    grouped: dict[str, list[Subscribe]] = {}
    for row in rows:
        if not row.uid:
            continue
        grouped.setdefault(row.uid, []).append(row)
    return grouped


def _subs_for_mode(subs: Sequence[Subscribe], mode: PriceMode) -> list[Subscribe]:
    return [sub for sub in subs if subscription_mode(sub.extra_data) == mode]


async def _load_baselines() -> dict[str, PriceBaseline]:
    """一次取回全部基线；任务名下只认 price: 前缀的行。"""
    rows = await SteamPoll.get_all(BASELINE_TASK)
    baselines: dict[str, PriceBaseline] = {}
    for row in rows:
        appid = appid_of_key(row.key)
        if appid is None:
            continue
        baselines[appid] = baseline_from_json(row.value)
    return baselines


async def _save_baselines(changed: dict[str, PriceBaseline]) -> None:
    for appid, baseline in changed.items():
        await SteamPoll.upsert(BASELINE_TASK, baseline_key(appid), baseline_to_json(baseline))


async def _prune_baselines(appids: set[str], baselines: dict[str, PriceBaseline]) -> None:
    """清理已退订游戏的基线，避免表随历史订阅无限增长。"""
    for appid in baselines:
        if appid not in appids:
            await SteamPoll.delete_row(BASELINE_TASK, baseline_key(appid))


async def _load_history_caches(appids: Sequence[str], cc: str) -> dict[str, HistoryLowCache]:
    caches: dict[str, HistoryLowCache] = {}
    for appid in appids:
        raw = await SteamCache.get_value(HISTORY_LOW_CACHE_TYPE, history_low_key(appid, cc))
        if raw:
            caches[appid] = history_low_from_json(raw)
    return caches


async def _save_history_cache(appid: str, cc: str, cache: HistoryLowCache) -> None:
    await SteamCache.upsert(
        HISTORY_LOW_CACHE_TYPE,
        history_low_key(appid, cc),
        history_low_to_json(cache),
        cache["checked_at"],
    )


async def _refresh_history_caches(
    appids: Sequence[str],
    caches: dict[str, HistoryLowCache],
    *,
    cc: str,
    now: int,
) -> set[str]:
    """补齐缺失或超过 24 小时的史低缓存，返回本轮首次建立的 appid。"""
    missing: list[str] = []
    for appid in appids:
        cache = caches[appid] if appid in caches else None
        if cache is None or needs_history_low_refresh(cache, now):
            missing.append(appid)
    if not missing:
        return set()

    try:
        games = await fetch_store_lows(missing, cc=cc)
    except (httpx.HTTPError, msgspec.ValidationError, ValueError) as error:
        logger.warning(f"{_TAG} 史低接口失败，{len(missing)} 个游戏将在 24 小时后重试: {type(error).__name__}")
        for appid in missing:
            cache = missing_history_low(now)
            caches[appid] = cache
            await _save_history_cache(appid, cc, cache)
        return set()

    initialized: set[str] = set()
    for appid in missing:
        game = games[appid] if appid in games else None
        cache = history_low_from_game(game, now)
        caches[appid] = cache
        await _save_history_cache(appid, cc, cache)
        if cache["status"] == "ok":
            initialized.add(appid)
    return initialized


async def _drop_card(drop: _Drop) -> PriceDropCard:
    """降价项出卡：名称与简介取缓存详情，名字缺失时补搜；封面经三级回退落 img_cache。"""
    cc = region_cc()
    detail = await load_store_detail(drop.appid, cc)
    desc = ""
    if detail is not None and "success" in detail and detail["success"] and "data" in detail:
        data = detail["data"]
        desc = clean_description(data["short_description"] if "short_description" in data else "")
    name = store_detail_name(detail) or await pics_game_name(drop.appid, lang=region_lang()) or drop.appid

    cover_name = await resolve_cover_name(
        drop.appid,
        country=cc,
        lang=region_lang(),
        griddb_key=griddb_cover_key(),
    )
    # 原价优先取本轮 initial_formatted，缺失时回落上一轮现价
    original = drop.previous["final_formatted"] if "final_formatted" in drop.previous else ""
    if "initial_formatted" in drop.current and drop.current["initial_formatted"]:
        original = drop.current["initial_formatted"]
    percent = drop.current["discount_percent"] if "discount_percent" in drop.current else 0
    return PriceDropCard(
        name=name,
        desc=desc if desc else _NO_DESC,
        cover_url=get_img_cache_url(cover_name) if cover_name else "",
        discount_percent=percent,
        original_price=original,
        final_price=price_text(drop.current),
    )


async def _push_drop(drop: _Drop, subs: Sequence[Subscribe]) -> None:
    """向指定模式订阅者推送价格卡；单个会话失败只记日志、不打断其余。"""
    card = await _drop_card(drop)
    image = await render_price_drop_card(card)
    percent = drop.current["discount_percent"] if "discount_percent" in drop.current else 0
    if percent > 0:
        change_text = f"现在打 {discount_label(percent)}，现价 {price_text(drop.current)}"
    else:
        change_text = f"现在降价，现价 {price_text(drop.current)}"
    for sub in subs:
        try:
            await sub.send(MessageSegment.image(image))
            await sub.send(
                [
                    MessageSegment.at(sub.user_id),
                    MessageSegment.text(
                        f"\n[Steam · 降价提醒] 你订阅的 {card.name} {change_text}\n"
                        f"商店链接：https://store.steampowered.com/app/{drop.appid}"
                    ),
                ]
            )
        except Exception as error:
            logger.warning(f"{_TAG} 推送失败 appid={drop.appid} user={sub.user_id}: {type(error).__name__}")


async def _poll_once() -> None:
    global _startup_pending

    subs_by_appid = _subscribers_by_appid(_subscribe_rows(await gs_subscribe.get_subscribe(SUBSCRIBE_TASK)))
    baselines = await _load_baselines()
    await _prune_baselines(set(subs_by_appid), baselines)
    if _startup_pending is None:
        _startup_pending = set(subs_by_appid)
    else:
        _startup_pending.intersection_update(subs_by_appid)
    if not subs_by_appid:
        return
    pending = _startup_pending

    appids = sorted(subs_by_appid)
    cc = region_cc()
    prices = await fetch_price_overviews(appids, cc=cc)
    caches = await _load_history_caches(appids, cc)
    now = int(time.time())
    initialized = await _refresh_history_caches(appids, caches, cc=cc, now=now)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    drops: list[_Drop] = []
    history_hits: list[_Drop] = []
    changed: dict[str, PriceBaseline] = {}
    changed_caches: dict[str, HistoryLowCache] = {}
    observed: set[str] = set()

    for appid in appids:
        entry = prices[appid] if appid in prices else None
        overview = price_overview(entry)
        # 免费 / 无价 / 锁区本轮拿不到价：跳过，保留原状态
        if overview is None:
            continue
        observed.add(appid)
        current = to_baseline(overview)
        previous = baselines[appid] if appid in baselines else None
        subs = subs_by_appid[appid]
        price_subs = _subs_for_mode(subs, "price")
        history_subs = _subs_for_mode(subs, "history")

        if previous is not None and appid not in pending and is_drop(previous, current) and price_subs:
            drops.append(_Drop(appid=appid, previous=previous, current=current))

        cache = caches[appid] if appid in caches else None
        if cache is not None and cache["status"] == "ok" and cache["lowest"] is not None:
            final = current["final"] if "final" in current else None
            if final is not None:
                lowest = cache["lowest"]
                if final < lowest:
                    cache["lowest"] = final
                    if "currency" in current:
                        cache["currency"] = current["currency"]
                    cache["timestamp"] = now_iso
                    if appid not in initialized and appid not in pending and history_subs:
                        history_hits.append(_Drop(appid=appid, previous=previous or current, current=current))
                    cache["at_low_notified"] = True
                    changed_caches[appid] = cache
                elif final > lowest:
                    if cache["at_low_notified"]:
                        cache["at_low_notified"] = False
                        changed_caches[appid] = cache
                elif not cache["at_low_notified"]:
                    if appid not in initialized and appid not in pending and history_subs:
                        history_hits.append(_Drop(appid=appid, previous=previous or current, current=current))
                    cache["at_low_notified"] = True
                    changed_caches[appid] = cache

        if previous is None or previous != current:
            changed[appid] = current

    await _save_baselines(changed)
    for appid, cache in changed_caches.items():
        await _save_history_cache(appid, cc, cache)
    pending.difference_update(observed)

    if not SteamConfig.get_config("PriceNotifySwitch").data:
        return
    for drop in drops:
        price_subs = _subs_for_mode(subs_by_appid[drop.appid], "price")
        if price_subs:
            await _push_drop(drop, price_subs)
    for hit in history_hits:
        history_subs = _subs_for_mode(subs_by_appid[hit.appid], "history")
        if history_subs:
            await _push_drop(hit, history_subs)


async def poll_price_once() -> None:
    """单轮价格轮询；异常在此收口，避免打断调度器。"""
    try:
        await _poll_once()
    except httpx.HTTPStatusError as error:
        logger.warning(f"{_TAG} 接口请求失败: HTTP {error.response.status_code}")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 网络请求失败: {type(error).__name__}")
    except Exception as error:
        logger.exception(f"{_TAG} 轮询异常: {type(error).__name__}")
