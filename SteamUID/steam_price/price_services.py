"""降价 / 史低订阅命令：模式覆盖、取消与列表卡片装配。"""

import asyncio
from datetime import datetime, timezone
from collections.abc import Sequence

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.database.models import Subscribe

from ..utils.api.models import AppDetailsEntry
from ..utils.helper.bind import (
    scope_name,
    scope_task_rows,
    add_scope_subscribe,
    scope_subscribe_rows,
    delete_scope_subscribe,
)
from ..utils.helper.game import GameRef, match_tip_text, resolve_game_ref
from ..utils.helper.price import (
    entry_data,
    format_price,
    price_fields,
    price_overview,
    fetch_price_overviews,
)
from ..utils.helper.config import region, region_cc, region_lang, griddb_cover_key
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.price_drop import (
    BASELINE_TASK,
    SUBSCRIBE_TASK,
    PriceMode,
    PriceBaseline,
    to_baseline,
    baseline_key,
    baseline_to_json,
    subscription_data,
    subscription_mode,
)
from ..utils.helper.game_detail import (
    load_store_detail,
    resolve_game_names,
    preferred_game_name,
    preferred_game_names,
)
from ..utils.helper.history_low import (
    HISTORY_LOW_CACHE_TYPE,
    history_low_key,
    history_low_to_json,
    history_low_from_json,
)
from ..utils.database.model_poll import SteamPoll
from ..utils.database.model_cache import SteamCache
from ..utils.render.html.price_list import (
    PriceEntry,
    PriceListCard,
    render_price_list_card,
)
from ..utils.render.html.static_assets import get_img_cache_url

_WRITE_USAGE = "steam订阅降价 艾尔登法环 或 steam订阅史低 艾尔登法环"
_FETCH_FAILED = "获取该游戏价格失败，请确认该游戏在当前地区是否锁区"
_NO_PRICE = "该游戏无可用价格（免费或未发售），无法订阅价格提醒"

# 商店详情逐游戏请求，分批并发与封面解析保持一致
_DETAIL_BATCH = 10


def _appids_of(rows: Sequence[Subscribe]) -> list[str]:
    """订阅行去重后的 appid 列表，保持首次出现顺序。"""
    appids: list[str] = []
    for row in rows:
        if row.uid and row.uid not in appids:
            appids.append(row.uid)
    return appids


def _modes_of(rows: Sequence[Subscribe]) -> dict[str, PriceMode]:
    modes: dict[str, PriceMode] = {}
    for row in rows:
        if row.uid and row.uid not in modes:
            modes[row.uid] = subscription_mode(row.extra_data)
    return modes


async def _load_details(appids: Sequence[str], cc: str) -> list[AppDetailsEntry | None]:
    """逐游戏取商店详情（命中缓存直接复用），分批并发；单条失败回落 None。"""
    sem = asyncio.Semaphore(_DETAIL_BATCH)

    async def one(appid: str) -> AppDetailsEntry | None:
        async with sem:
            return await load_store_detail(appid, cc)

    return list(await asyncio.gather(*(one(appid) for appid in appids)))


async def _resolve_ref(bot: Bot, ev: Event) -> GameRef:
    """解析目标游戏；走了商店搜索时先回执可能命中的结果。"""
    raw = ev.text.strip()
    if not raw:
        raise ValueError(f"请输入游戏名或 AppID，例如：{_WRITE_USAGE}")

    ref = await resolve_game_ref(raw, cc=region_cc())
    if not raw.isdigit():
        await bot.send(match_tip_text(ref))
    return ref


async def _display_name(ref: GameRef) -> str:
    """订阅回执的游戏名：开关开启时优先 steamcmd，失败保留搜索命中名。"""
    return await preferred_game_name(ref.appid, fallback=ref.name, lang=region_lang())


def _mode_label(mode: PriceMode) -> str:
    return "史低提醒" if mode == "history" else "降价提醒"


async def _initialize_history_mode(appid: str, baseline: PriceBaseline) -> None:
    """首次建立史低订阅时吸收当前史低，不触发轮询推送。"""
    if "final" not in baseline:
        return
    key = history_low_key(appid, region_cc())
    raw = await SteamCache.get_value(HISTORY_LOW_CACHE_TYPE, key)
    if not raw:
        return

    cache = history_low_from_json(raw)
    if cache["status"] != "ok" or cache["lowest"] is None:
        return

    final = baseline["final"]
    changed = False
    if final < cache["lowest"]:
        cache["lowest"] = final
        if "currency" in baseline:
            cache["currency"] = baseline["currency"]
        cache["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        changed = True
    if final <= cache["lowest"]:
        if not cache["at_low_notified"]:
            cache["at_low_notified"] = True
            changed = True
    elif cache["at_low_notified"]:
        cache["at_low_notified"] = False
        changed = True

    if changed:
        cache["checked_at"] = int(datetime.now(timezone.utc).timestamp())
        await SteamCache.upsert(
            HISTORY_LOW_CACHE_TYPE,
            key,
            history_low_to_json(cache),
            cache["checked_at"],
        )


def _entry(
    appid: str,
    detail: AppDetailsEntry | None,
    live: AppDetailsEntry | None,
    cover_url: str,
    name: str,
    mode: PriceMode,
    *,
    currency: str,
) -> PriceEntry:
    """单行数据：名称由调用方解析，免费 / 未发售取缓存详情，售价取实时批量价。"""
    data = entry_data(detail)
    kind, text, percent = price_fields(data, price_overview(live), currency=currency)
    return PriceEntry(
        appid=appid,
        name=name,
        cover_url=cover_url,
        price_text=text,
        price_kind=kind,
        discount_percent=percent,
        mode=mode,
    )


async def _subscribe(bot: Bot, ev: Event, mode: PriceMode) -> None:
    ref = await _resolve_ref(bot, ev)
    display_name = await _display_name(ref)
    rows = await scope_subscribe_rows(ev, SUBSCRIBE_TASK, ref.appid)
    old_mode = subscription_mode(rows[0].extra_data) if rows else None
    if old_mode == mode:
        await bot.send(f"{scope_name(ev)}已订阅该游戏：{display_name}({ref.appid})")
        return

    prices = await fetch_price_overviews([ref.appid], cc=region_cc())
    entry = prices[ref.appid] if ref.appid in prices else None
    if entry is None or "success" not in entry or not entry["success"]:
        raise ValueError(_FETCH_FAILED)
    data = entry_data(entry)
    if data is not None and "is_free" in data and data["is_free"]:
        raise ValueError(_NO_PRICE)
    overview = price_overview(entry)
    if overview is None:
        raise ValueError(_NO_PRICE)

    await add_scope_subscribe(
        ev,
        SUBSCRIBE_TASK,
        ref.appid,
        extra_data=subscription_data(mode),
    )
    baseline = to_baseline(overview)
    await SteamPoll.upsert(BASELINE_TASK, baseline_key(ref.appid), baseline_to_json(baseline))
    if mode == "history":
        await _initialize_history_mode(ref.appid, baseline)

    price = format_price(overview, region().currency)
    if old_mode is None:
        message = f"已为{scope_name(ev)}订阅【{display_name}】({ref.appid}) {_mode_label(mode)}，当前售价 {price}"
    else:
        message = (
            f"已将{scope_name(ev)}对【{display_name}】({ref.appid})的推送模式改为{_mode_label(mode)}，当前售价 {price}"
        )
    await bot.send(message)


async def subscribe_price(bot: Bot, ev: Event) -> None:
    """steam订阅降价<游戏名/AppID>：订阅或覆盖为降价提醒。"""
    await _subscribe(bot, ev, "price")


async def subscribe_history(bot: Bot, ev: Event) -> None:
    """steam订阅史低<游戏名/AppID>：订阅或覆盖为史低提醒。"""
    await _subscribe(bot, ev, "history")


async def _unsubscribe(bot: Bot, ev: Event, mode: PriceMode) -> None:
    ref = await _resolve_ref(bot, ev)
    display_name = await _display_name(ref)
    rows = await scope_subscribe_rows(ev, SUBSCRIBE_TASK, ref.appid)
    if not rows or subscription_mode(rows[0].extra_data) != mode:
        await bot.send(f"{scope_name(ev)}未订阅该游戏：{display_name}({ref.appid})")
        return
    await delete_scope_subscribe(ev, SUBSCRIBE_TASK, ref.appid)
    await bot.send(f"已取消{scope_name(ev)}订阅的【{display_name}】({ref.appid}) {_mode_label(mode)}")


async def unsubscribe_price(bot: Bot, ev: Event) -> None:
    """steam取消订阅降价<游戏名/AppID>：只取消降价模式。"""
    await _unsubscribe(bot, ev, "price")


async def unsubscribe_history(bot: Bot, ev: Event) -> None:
    """steam取消订阅史低<游戏名/AppID>：只取消史低模式。"""
    await _unsubscribe(bot, ev, "history")


async def build_price_list_card(ev: Event) -> bytes:
    """steam订阅降价查看：本会话订阅、推送模式与当前售价渲染成卡片。"""
    rows = await scope_task_rows(ev, SUBSCRIBE_TASK)
    appids = _appids_of(rows)
    if not appids:
        raise ValueError(f"{scope_name(ev)}当前没有订阅任何价格提醒")
    modes = _modes_of(rows)

    cc = region_cc()
    prices, covers, details = await asyncio.gather(
        fetch_price_overviews(appids, cc=cc),
        resolve_cover_names(appids, country=cc, lang=region_lang(), griddb_key=griddb_cover_key()),
        _load_details(appids, cc),
    )
    names = await resolve_game_names(appids, cc=cc, lang=region_lang(), details=dict(zip(appids, details)))
    names = await preferred_game_names(
        appids,
        fallbacks={appid: names[appid] if appid in names else appid for appid in appids},
        lang=region_lang(),
    )
    currency = region().currency
    entries = [
        _entry(
            appid,
            details[index],
            prices[appid] if appid in prices else None,
            get_img_cache_url(covers[appid]) if appid in covers else "",
            names[appid] if appid in names else appid,
            modes[appid] if appid in modes else "price",
            currency=currency,
        )
        for index, appid in enumerate(appids)
    ]
    return await render_price_list_card(PriceListCard(entries=entries))
