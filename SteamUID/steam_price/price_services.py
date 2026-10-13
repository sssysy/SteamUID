"""降价订阅命令：订阅增删的校验写入与订阅列表卡片装配。"""

import asyncio
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
    to_baseline,
    baseline_key,
    baseline_to_json,
)
from ..utils.helper.game_detail import load_store_detail, resolve_game_names
from ..utils.database.model_poll import SteamPoll
from ..utils.render.html.price_list import (
    PriceEntry,
    PriceListCard,
    render_price_list_card,
)
from ..utils.render.html.static_assets import get_img_cache_url

_WRITE_USAGE = "steam订阅降价 艾尔登法环 或 steam取消订阅降价 730"
_FETCH_FAILED = "获取该游戏价格失败，请确认该游戏在当前地区是否锁区"
_NO_PRICE = "该游戏无可用价格（免费或未发售），无法订阅降价提醒"

# 商店详情逐游戏请求，分批并发与封面解析保持一致
_DETAIL_BATCH = 10


def _appids_of(rows: Sequence[Subscribe]) -> list[str]:
    """订阅行去重后的 appid 列表，保持首次出现顺序。"""
    appids: list[str] = []
    for row in rows:
        if row.uid and row.uid not in appids:
            appids.append(row.uid)
    return appids


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


async def _is_subscribed(ev: Event, appid: str) -> bool:
    """当前会话是否已订阅该 appid 的降价提醒。"""
    return bool(await scope_subscribe_rows(ev, SUBSCRIBE_TASK, appid))


def _entry(
    appid: str,
    detail: AppDetailsEntry | None,
    live: AppDetailsEntry | None,
    cover_url: str,
    name: str,
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
    )


async def subscribe_price(bot: Bot, ev: Event) -> None:
    """steam订阅降价<游戏名/AppID>：订阅该游戏的降价提醒。"""
    ref = await _resolve_ref(bot, ev)
    if await _is_subscribed(ev, ref.appid):
        await bot.send(f"{scope_name(ev)}已订阅该游戏：{ref.name}({ref.appid})")
        return

    prices = await fetch_price_overviews([ref.appid], cc=region_cc())
    entry = prices[ref.appid] if ref.appid in prices else None
    if entry is None or "success" not in entry or not entry["success"]:
        raise ValueError(_FETCH_FAILED)
    overview = price_overview(entry)
    if overview is None:
        raise ValueError(_NO_PRICE)

    await add_scope_subscribe(ev, SUBSCRIBE_TASK, ref.appid)
    baseline = to_baseline(overview)
    await SteamPoll.upsert(BASELINE_TASK, baseline_key(ref.appid), baseline_to_json(baseline))
    await bot.send(
        f"已为{scope_name(ev)}订阅【{ref.name}】({ref.appid}) 降价提醒，当前售价 {format_price(overview, region().currency)}"
    )


async def unsubscribe_price(bot: Bot, ev: Event) -> None:
    """steam取消订阅降价<游戏名/AppID>：取消订阅该游戏的降价提醒。"""
    ref = await _resolve_ref(bot, ev)
    if not await _is_subscribed(ev, ref.appid):
        await bot.send(f"{scope_name(ev)}未订阅该游戏：{ref.name}({ref.appid})")
        return
    await delete_scope_subscribe(ev, SUBSCRIBE_TASK, ref.appid)
    await bot.send(f"已取消{scope_name(ev)}订阅的【{ref.name}】({ref.appid}) 降价提醒")


async def build_price_list_card(ev: Event) -> bytes:
    """steam订阅降价查看：本会话订阅的降价与当前售价渲染成卡片。"""
    rows = await scope_task_rows(ev, SUBSCRIBE_TASK)
    appids = _appids_of(rows)
    if not appids:
        raise ValueError(f"{scope_name(ev)}当前没有订阅任何降价提醒")

    cc = region_cc()
    prices, covers, details = await asyncio.gather(
        fetch_price_overviews(appids, cc=cc),
        resolve_cover_names(appids, country=cc, griddb_key=griddb_cover_key()),
        _load_details(appids, cc),
    )
    names = await resolve_game_names(appids, cc=cc, lang=region_lang(), details=dict(zip(appids, details)))
    currency = region().currency
    entries = [
        _entry(
            appid,
            details[index],
            prices[appid] if appid in prices else None,
            get_img_cache_url(covers[appid]) if appid in covers else "",
            names[appid] if appid in names else appid,
            currency=currency,
        )
        for index, appid in enumerate(appids)
    ]
    return await render_price_list_card(PriceListCard(entries=entries))
