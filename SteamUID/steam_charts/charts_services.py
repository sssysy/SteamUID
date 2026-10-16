"""steam 榜单：周热销 / 当前在线 / 本周活跃三个榜单的取数与出图。"""

import datetime
from dataclasses import dataclass
from collections.abc import Callable, Sequence

from gsuid_core.logger import logger

from ..steam_config import SteamConfig
from ..utils.api.cover import build_store_item_asset_url
from ..utils.api.models import (
    AppDetailsEntry,
    StoreBrowseItem,
    MostPlayedPayload,
    WeeklyTopSellersPayload,
    ConcurrentPlayersPayload,
)
from ..utils.downloader import download
from ..utils.helper.price import price_overview, fetch_price_overviews
from ..utils.helper.charts import (
    load_most_played,
    previous_week_start,
    load_concurrent_players,
    load_weekly_top_sellers,
)
from ..utils.helper.config import region_cc, region_lang, griddb_cover_key
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.game_detail import clean_description
from ..utils.render.html.charts_grid import (
    ChartGame,
    ChartRank,
    ChartPrice,
    ChartValue,
    ChartPlayers,
    render_steam_charts,
)
from ..utils.render.html.static_assets import get_bg_url, get_img_cache_url

_TAG = "[Steam·排行榜]"

# 3×3 宫格固定 9 条，不传参
_SLOTS = 9
# 过滤规则：只保留游戏 / DLC / 软件
_KEEP_TYPES = frozenset({0, 4, 6})
# 过滤后仍需补满 9 条，多取一段候选供封面缺失时往下补位
_CANDIDATES = 15


@dataclass(frozen=True)
class _Picked:
    """候选条目：Steam 真实名次 / 条目本体 / 上周名次 / 当前在线与峰值。"""

    rank: int
    item: StoreBrowseItem
    last_rank: int = 0
    concurrent: int = 0
    peak: int = 0


def _settings() -> tuple[list[str], int, str, str]:
    """一次取出密钥池、冷却与地区语言，避免各分支重复读配置。"""
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")
    return keys, SteamConfig.get_config("KeyPoolCooldown").data, region_cc(), region_lang()


def _date_of(timestamp: int) -> str:
    """UTC 日期文本；时间戳缺失时回落空串。"""
    if not timestamp:
        return ""
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).strftime("%Y-%m-%d")


def _appid_of(item: StoreBrowseItem) -> str:
    return str(item["appid"]) if "appid" in item else ""


def _name_of(item: StoreBrowseItem) -> str:
    return item["name"] if "name" in item else ""


def _description_of(item: StoreBrowseItem) -> str:
    """简介：清掉商店文案里的 HTML 残留；条目没带简介时留空。"""
    if "basic_info" not in item:
        return ""
    info = item["basic_info"]
    if "short_description" not in info:
        return ""
    return clean_description(info["short_description"])


def _asset_cover_url(item: StoreBrowseItem) -> str:
    """榜单条目自带的封面直链：优先横板 header，再退主胶囊 / 小胶囊。"""
    if "assets" not in item:
        return ""
    assets = item["assets"]
    fmt = assets["asset_url_format"] if "asset_url_format" in assets else ""
    name = ""
    if "header" in assets:
        name = assets["header"]
    elif "main_capsule" in assets:
        name = assets["main_capsule"]
    elif "small_capsule" in assets:
        name = assets["small_capsule"]
    if not fmt or not name:
        return ""
    return build_store_item_asset_url(fmt, name)


def _sale_rows(payload: WeeklyTopSellersPayload) -> list[_Picked]:
    rows = payload["ranks"] if "ranks" in payload else []
    return [_Picked(rank=entry["rank"], item=entry["item"]) for entry in rows if "rank" in entry and "item" in entry]


def _now_rows(payload: ConcurrentPlayersPayload) -> list[_Picked]:
    rows = payload["ranks"] if "ranks" in payload else []
    return [
        _Picked(
            rank=entry["rank"],
            item=entry["item"],
            concurrent=entry["concurrent_in_game"] if "concurrent_in_game" in entry else 0,
            peak=entry["peak_in_game"] if "peak_in_game" in entry else 0,
        )
        for entry in rows
        if "rank" in entry and "item" in entry
    ]


def _week_rows(payload: MostPlayedPayload) -> list[_Picked]:
    rows = payload["ranks"] if "ranks" in payload else []
    return [
        _Picked(
            rank=entry["rank"],
            item=entry["item"],
            last_rank=entry["last_week_rank"] if "last_week_rank" in entry else 0,
            peak=entry["peak_in_game"] if "peak_in_game" in entry else 0,
        )
        for entry in rows
        if "rank" in entry and "item" in entry
    ]


def _pick(rows: Sequence[_Picked]) -> list[_Picked]:
    """按 type 过滤非游戏条目，保留 Steam 真实名次并多取候选。"""
    picked: list[_Picked] = []
    for row in rows:
        if "type" not in row.item or row.item["type"] not in _KEEP_TYPES:
            continue
        picked.append(row)
        if len(picked) >= _CANDIDATES:
            break
    return picked


async def _resolve_covers(picked: Sequence[_Picked]) -> dict[str, str]:
    """封面落 img_cache：先用榜单自带直链，空结果再走商店详情 / 社区封面兜底。"""
    appids = [_appid_of(row.item) for row in picked]
    urls = [_asset_cover_url(row.item) for row in picked]
    paths = await download(urls, kind="image")

    covers: dict[str, str] = {}
    missing: list[str] = []
    for appid, path in zip(appids, paths, strict=True):
        if not appid:
            continue
        if path is None:
            missing.append(appid)
            continue
        covers[appid] = path.name

    if missing:
        fallback = await resolve_cover_names(
            missing, country=region_cc(), lang=region_lang(), griddb_key=griddb_cover_key()
        )
        covers.update({appid: name for appid, name in fallback.items() if name})
    return covers


def _fill_slots(picked: Sequence[_Picked], covers: dict[str, str]) -> list[_Picked]:
    """按名次顺序补满 9 条；封面拿不到的跳过，由后面的候选顶上来。"""
    filled: list[_Picked] = []
    for row in picked:
        appid = _appid_of(row.item)
        if appid and appid in covers:
            filled.append(row)
        if len(filled) >= _SLOTS:
            break
    return filled


def _card(row: _Picked, covers: dict[str, str], value: ChartValue) -> ChartGame:
    """组装一格：封面取挂载直链，名次直接用 Steam 真实名次。"""
    return ChartGame(
        rank=row.rank,
        name=_name_of(row.item),
        description=_description_of(row.item),
        cover_url=get_img_cache_url(covers[_appid_of(row.item)]),
        value=value,
    )


def _sale_value(item: StoreBrowseItem, prices: dict[str, AppDetailsEntry]) -> ChartPrice:
    """价格行：免费 -> 折扣或标价；商店详情查不到时回落榜单自带价。"""
    if "is_free" in item and item["is_free"]:
        return ChartPrice(is_free=True, price_text="", original_text="", discount_percent=0)

    appid = _appid_of(item)
    overview = price_overview(prices[appid] if appid in prices else None)
    if overview is not None:
        final = overview["final_formatted"] if "final_formatted" in overview else ""
        percent = overview["discount_percent"] if "discount_percent" in overview else 0
        original = overview["initial_formatted"] if "initial_formatted" in overview else ""
        if final:
            return ChartPrice(
                is_free=False,
                price_text=final,
                original_text=original if percent > 0 else "",
                discount_percent=percent,
            )

    option = item["best_purchase_option"] if "best_purchase_option" in item else None
    if option is not None:
        text = option["formatted_final_price"] if "formatted_final_price" in option else ""
        if text:
            return ChartPrice(is_free=False, price_text=text, original_text="", discount_percent=0)
    return ChartPrice(is_free=False, price_text="", original_text="", discount_percent=0)


def _hot_value(period: str) -> Callable[[_Picked], ChartValue]:
    """热门榜数值行：当前实时给在线 / 峰值，本周给峰值与名次升降。"""
    if period == "当前":
        return lambda row: ChartPlayers(concurrent=row.concurrent, peak=row.peak)
    return lambda row: ChartRank(peak=row.peak, delta=row.last_rank - row.rank if row.last_rank else 0)


async def build_hot_chart(period: str) -> bytes:
    """热门排行出图：period 取 本周（活跃）/ 当前（在线）。"""
    keys, cooldown, cc, lang = _settings()

    if period == "当前":
        payload = await load_concurrent_players(keys=keys, cooldown=cooldown, country_code=cc, lang=lang)
        picked = _pick(_now_rows(payload))
        subtitle = "当前实时 · 全球"
    else:
        payload = await load_most_played(keys=keys, cooldown=cooldown, country_code=cc, lang=lang)
        picked = _pick(_week_rows(payload))
        rollup = payload["rollup_date"] if "rollup_date" in payload else 0
        subtitle = f"本周 · 截至 {_date_of(rollup)}"

    covers = await _resolve_covers(picked)
    filled = _fill_slots(picked, covers)
    if not filled:
        raise ValueError("热门榜暂时取不到数据")
    if len(filled) < _SLOTS:
        logger.info(f"{_TAG} {period}热门榜过滤后只有 {len(filled)} 条")

    build_value = _hot_value(period)
    games = [_card(row, covers, build_value(row)) for row in filled]
    return await render_steam_charts("Steam 热门排行", subtitle, games, card_bg_url=get_bg_url())


async def build_sale_chart(period: str) -> bytes:
    """热销排行出图：period 取 本周（最近一周）/ 上周。"""
    keys, cooldown, cc, lang = _settings()

    start: int | None = None
    if period == "上周":
        latest = await load_weekly_top_sellers(keys=keys, cooldown=cooldown, country_code=cc, lang=lang)
        start = previous_week_start(latest["start_date"] if "start_date" in latest else 0)
    payload = await load_weekly_top_sellers(
        keys=keys,
        cooldown=cooldown,
        country_code=cc,
        lang=lang,
        start_date=start,
    )

    picked = _pick(_sale_rows(payload))
    covers = await _resolve_covers(picked)
    filled = _fill_slots(picked, covers)
    if not filled:
        raise ValueError("热销榜暂时取不到数据")
    if len(filled) < _SLOTS:
        logger.info(f"{_TAG} {period}热销榜过滤后只有 {len(filled)} 条")

    prices = await fetch_price_overviews([_appid_of(row.item) for row in filled], cc=cc)
    games = [_card(row, covers, _sale_value(row.item, prices)) for row in filled]

    return await render_steam_charts("Steam 热销排行", period, games, card_bg_url=get_bg_url())
