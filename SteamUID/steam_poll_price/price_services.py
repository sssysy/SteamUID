"""游戏降价轮询：拉取价格、比对基线、出图推送与基线维护的编排。"""

from dataclasses import dataclass
from collections.abc import Sequence

import httpx

from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..steam_config import SteamConfig
from ..utils.helper.price import price_overview, fetch_price_overviews
from ..utils.helper.config import region_cc, griddb_cover_key
from ..utils.helper.game_cover import resolve_cover_name
from ..utils.helper.price_drop import (
    BASELINE_TASK,
    SUBSCRIBE_TASK,
    PriceBaseline,
    is_drop,
    price_text,
    to_baseline,
    appid_of_key,
    baseline_key,
    baseline_to_json,
    baseline_from_json,
)
from ..utils.helper.game_detail import clean_description, load_store_detail
from ..utils.database.model_poll import SteamPoll
from ..utils.render.html.price_drop import PriceDropCard, render_price_drop_card
from ..utils.render.html.static_assets import get_img_cache_url

_TAG = "[Steam·降价轮询]"
_NO_DESC = "暂无游戏简介"


@dataclass(frozen=True)
class _Drop:
    """一轮比对里的一个降价项：appid + 旧基线 + 新基线。"""

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


async def _collect(
    appids: Sequence[str],
    baselines: dict[str, PriceBaseline],
) -> tuple[list[_Drop], dict[str, PriceBaseline]]:
    """拉取一轮价格并与基线比对，返回降价项与需要回写的基线。"""
    prices = await fetch_price_overviews(appids, cc=region_cc())
    drops: list[_Drop] = []
    changed: dict[str, PriceBaseline] = {}
    for appid in appids:
        entry = prices[appid] if appid in prices else None
        overview = price_overview(entry)
        # 免费 / 无价 / 锁区本轮拿不到价：跳过，保留原基线
        if overview is None:
            continue
        current = to_baseline(overview)
        previous = baselines[appid] if appid in baselines else None
        if previous is not None and is_drop(previous, current):
            drops.append(_Drop(appid=appid, previous=previous, current=current))
        if previous is None or previous != current:
            changed[appid] = current
    return drops, changed


async def _drop_card(drop: _Drop) -> PriceDropCard:
    """降价项出卡：名称与简介取缓存详情，封面经三级回退落 img_cache。"""
    cc = region_cc()
    detail = await load_store_detail(drop.appid, cc)
    name = drop.appid
    desc = ""
    if detail is not None and "success" in detail and detail["success"] and "data" in detail:
        data = detail["data"]
        name = data["name"] if "name" in data else drop.appid
        desc = clean_description(data["short_description"] if "short_description" in data else "")

    cover_name = await resolve_cover_name(
        drop.appid,
        country=cc,
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
    """向该游戏的全部订阅者推送降价卡；单个会话失败只记日志、不打断其余。"""
    card = await _drop_card(drop)
    image = await render_price_drop_card(card)
    for sub in subs:
        message = [
            MessageSegment.at(sub.user_id),
            MessageSegment.text(f"\n[Steam 降价提醒] {card.name} 降价了！\n"),
            MessageSegment.image(image),
            MessageSegment.text(f"商店链接：https://store.steampowered.com/app/{drop.appid}"),
        ]
        try:
            await sub.send(message)
        except Exception as error:
            logger.warning(f"{_TAG} 推送失败 appid={drop.appid} user={sub.user_id}: {type(error).__name__}")


async def _poll_once() -> None:
    subs_by_appid = _subscribers_by_appid(_subscribe_rows(await gs_subscribe.get_subscribe(SUBSCRIBE_TASK)))
    baselines = await _load_baselines()
    await _prune_baselines(set(subs_by_appid), baselines)
    if not subs_by_appid:
        return

    appids = sorted(subs_by_appid)
    drops, changed = await _collect(appids, baselines)
    await _save_baselines(changed)

    if not SteamConfig.get_config("PriceNotifySwitch").data:
        return
    for drop in drops:
        await _push_drop(drop, subs_by_appid[drop.appid])


async def poll_price_once() -> None:
    """单轮降价轮询；异常在此收口，避免打断调度器。"""
    try:
        await _poll_once()
    except httpx.HTTPStatusError as error:
        logger.warning(f"{_TAG} 接口请求失败: HTTP {error.response.status_code}")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 网络请求失败: {type(error).__name__}")
    except Exception as error:
        logger.exception(f"{_TAG} 轮询异常: {type(error).__name__}")
