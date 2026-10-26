"""愿望单命令聚合：列表拉取与出图、增删校验与写入，凭据优先读取私密愿望单。"""

import asyncio
from functools import partial
from collections.abc import Sequence

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..steam_config import SteamConfig
from ..utils.api.models import (
    WishlistItem,
    AppDetailsEntry,
)
from ..utils.api.public import get_price_overview
from ..utils.helper.bind import is_logged_in, get_main_steamid64
from ..utils.helper.game import GameRef, match_tip_text, resolve_game_ref
from ..utils.api.wishlist import (
    add_to_wishlist,
    remove_from_wishlist,
    get_wishlist_with_token,
)
from ..utils.helper.price import (
    entry_data,
    price_fields,
    price_overview,
)
from ..utils.helper.config import region, api_base, region_cc, store_base, region_lang, griddb_cover_key
from ..utils.helper.command import resolve_viewer
from ..utils.helper.profile import SteamProfile, load_profile_assets, load_card_background_name
from ..utils.helper.steam_api import fetch_wishlist
from ..utils.helper.auth_token import run_with_token
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.game_detail import (
    load_store_detail,
    resolve_game_names,
    preferred_game_name,
    preferred_game_names,
)
from ..utils.render.html.wishlist import (
    WishlistCard,
    WishlistEntry,
    render_wishlist_card,
)
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.static_assets import get_img_cache_url, resolve_card_bg_url, get_default_avatar_url

_TAG = "[Steam·愿望单]"

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
# 商店详情逐游戏请求，分批并发与封面解析保持一致
_DETAIL_BATCH = 10
_LIST_USAGE = "steam愿望单列表 [条数]"
_WRITE_USAGE = "steam增加愿望单 730 或 steam删除愿望单 艾尔登法环"
_NOT_LOGGED_IN = "未检测到该账号的登录授权，请先发送 steam登录 完成网页授权"
_AUTH_EXPIRED = "Steam 登录授权已失效，请重新发送 steam登录 后再试"


def parse_limit(words: Sequence[str]) -> int:
    """条数实参：空参取默认，非数字、多于一个或超出 1-100 报用法错误。"""
    if not words:
        return _DEFAULT_LIMIT
    if len(words) > 1 or not words[0].isdigit():
        raise ValueError(f"参数错误，正确用法：{_LIST_USAGE}")
    limit = int(words[0])
    if limit < 1 or limit > _MAX_LIMIT:
        raise ValueError(f"条数需在 1-{_MAX_LIMIT} 之间，正确用法：{_LIST_USAGE}")
    return limit


def _date_added_of(item: WishlistItem) -> int:
    """排序键：愿望单添加时间戳，缺失视为最旧。"""
    return item["date_added"] if "date_added" in item else 0


def _build_entry(
    appid: str,
    added_ts: int,
    detail: AppDetailsEntry | None,
    live: AppDetailsEntry | None,
    cover_url: str,
    name: str,
    *,
    currency: str,
) -> WishlistEntry:
    """单行数据：名称由调用方解析，免费 / 未发售取缓存详情，售价取实时批量价。"""
    data = entry_data(detail)
    kind, text, percent = price_fields(data, price_overview(live), currency=currency)
    return WishlistEntry(
        appid=appid,
        name=name,
        cover_url=cover_url,
        added_ts=added_ts,
        price_text=text,
        price_kind=kind,
        discount_percent=percent,
    )


def _pill_account(profile: SteamProfile) -> PillAccount:
    """资料 -> 胶囊数据，图片字段统一转 img_cache 直链。"""
    return PillAccount(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=get_img_cache_url(profile.background_name),
    )


async def _fetch_by_token(steamid64: str) -> list[WishlistItem] | None:
    """用本人凭据查询愿望单（能读私密）；无凭据或凭据失效返回 None。"""

    async def query(token: str) -> list[WishlistItem]:
        return await get_wishlist_with_token(steamid64, access_token=token, base_url=api_base())

    return await run_with_token(steamid64, query)


async def _fetch_items(steamid64: str, *, own_account: bool) -> list[WishlistItem]:
    """取愿望单：本人的凭据优先，查询失败回落公开 Key；他人只能走公开 Key。"""
    if own_account:
        try:
            items = await _fetch_by_token(steamid64)
        except (httpx.HTTPError, ValueError) as error:
            logger.warning(f"{_TAG} 凭据查询愿望单失败，回落公开 Key: {type(error).__name__}")
            items = None
        if items is not None:
            return items
    return await fetch_wishlist(
        steamid64,
        keys=SteamConfig.get_config("SteamAPIKey").data,
        cooldown=SteamConfig.get_config("KeyPoolCooldown").data,
    )


async def _load_details(appids: Sequence[str], *, cc: str) -> list[AppDetailsEntry | None]:
    """逐游戏取商店详情（命中缓存直接复用），分批并发；单条失败回落 None。"""
    sem = asyncio.Semaphore(_DETAIL_BATCH)

    async def one(appid: str) -> AppDetailsEntry | None:
        async with sem:
            return await load_store_detail(appid, cc)

    return list(await asyncio.gather(*(one(appid) for appid in appids)))


async def build_wishlist_card(ev: Event, *, allow_at: bool) -> bytes:
    """steam愿望单列表[条数]：目标账号的愿望单与当前售价渲染成卡片。"""
    if not SteamConfig.get_config("SteamAPIKey").data:
        raise ValueError("请先配置 Steam API Key")

    user_id = resolve_viewer(ev, allow_at=allow_at)
    steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        if user_id == ev.user_id:
            raise ValueError("您在当前群未绑定 Steam 账号，请先绑定")
        raise ValueError("对方在当前群未绑定 Steam 账号")

    limit = parse_limit(ev.text.split())
    items = await _fetch_items(steamid64, own_account=user_id == ev.user_id)
    if not items:
        raise ValueError("该账号愿望单为空或未公开")

    ordered = sorted(items, key=_date_added_of, reverse=True)
    shown = ordered[:limit]
    hidden = len(ordered) - len(shown)
    appids = [str(item["appid"]) for item in shown]

    cc = region_cc()
    griddb_key = griddb_cover_key()
    details, prices, covers, profile, card_bg_name = await asyncio.gather(
        _load_details(appids, cc=cc),
        get_price_overview(appids, cc=cc, base_url=store_base()),
        resolve_cover_names(appids, country=cc, lang=region_lang(), griddb_key=griddb_key),
        load_profile_assets(steamid64),
        load_card_background_name(steamid64),
    )
    names = await resolve_game_names(appids, cc=cc, lang=region_lang(), details=dict(zip(appids, details)))
    names = await preferred_game_names(
        appids,
        fallbacks={appid: names[appid] if appid in names else appid for appid in appids},
        lang=region_lang(),
    )

    currency = region().currency
    entries = [
        _build_entry(
            appid,
            _date_added_of(item),
            details[index],
            prices[appid] if appid in prices else None,
            get_img_cache_url(covers[appid]) if appid in covers else "",
            names[appid] if appid in names else appid,
            currency=currency,
        )
        for index, (item, appid) in enumerate(zip(shown, appids))
    ]
    return await render_wishlist_card(
        _pill_account(profile),
        WishlistCard(total=len(ordered), hidden=hidden, entries=entries),
        card_bg_url=resolve_card_bg_url(card_bg_name),
    )


async def _checked_target(bot: Bot, ev: Event) -> tuple[str, GameRef]:
    """增删公共前置：本人主账号 + 登录凭据 + 游戏解析与匹配提示。"""
    steamid64 = await get_main_steamid64(ev, ev.user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")
    if not await is_logged_in(steamid64):
        raise ValueError(_NOT_LOGGED_IN)

    raw = ev.text.strip()
    if not raw:
        raise ValueError(f"请输入游戏名或 AppID，例如：{_WRITE_USAGE}")

    ref = await resolve_game_ref(raw, cc=region_cc())
    if not raw.isdigit():
        await bot.send(match_tip_text(ref))
    return steamid64, ref


async def _display_name(ref: GameRef) -> str:
    """愿望单回执的游戏名：开关开启时优先 steamcmd，失败保留搜索命中名。"""
    return await preferred_game_name(ref.appid, fallback=ref.name, lang=region_lang())


async def _load_own_items(steamid64: str) -> list[WishlistItem]:
    """增删校验用本人凭据读愿望单；读取失败直接报错，不盲目写入。"""
    items = await _fetch_by_token(steamid64)
    if items is None:
        raise ValueError(_AUTH_EXPIRED)
    return items


def _in_wishlist(items: Sequence[WishlistItem], appid: str) -> bool:
    """愿望单里是否已有该 appid。"""
    return any(str(item["appid"]) == appid for item in items)


async def add_wishlist_game(bot: Bot, ev: Event) -> None:
    """steam增加愿望单<游戏名/AppID>：把游戏加入自己账号的愿望单。"""
    steamid64, ref = await _checked_target(bot, ev)
    display_name = await _display_name(ref)
    if _in_wishlist(await _load_own_items(steamid64), ref.appid):
        await bot.send(f"该游戏已在愿望单中：{display_name}({ref.appid})")
        return

    if await run_with_token(steamid64, partial(add_to_wishlist, appid=int(ref.appid), base_url=api_base())) is None:
        raise ValueError(_AUTH_EXPIRED)
    await bot.send(f"已将 {display_name}({ref.appid}) 加入愿望单")


async def remove_wishlist_game(bot: Bot, ev: Event) -> None:
    """steam删除愿望单<游戏名/AppID>：把游戏移出自己账号的愿望单。"""
    steamid64, ref = await _checked_target(bot, ev)
    display_name = await _display_name(ref)
    if not _in_wishlist(await _load_own_items(steamid64), ref.appid):
        await bot.send(f"该游戏不在愿望单中：{display_name}({ref.appid})")
        return

    if (
        await run_with_token(steamid64, partial(remove_from_wishlist, appid=int(ref.appid), base_url=api_base()))
        is None
    ):
        raise ValueError(_AUTH_EXPIRED)
    await bot.send(f"已将 {display_name}({ref.appid}) 从愿望单移除")
