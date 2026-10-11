"""状态变化推送编排：把筛选后的事件渲染成文字或图片并逐会话发出。

放在渲染层是因为组装消息要用到卡片渲染与静态资源直链，按依赖方向 helper 不能反向引用。
"""

import asyncio
from collections.abc import Sequence

from gsuid_core.logger import logger
from gsuid_core.models import Message
from gsuid_core.segment import MessageSegment

from ..downloader import download
from ..helper.notify import Delivery, build_message, cd_mark, collect_deliveries
from ..helper.game_cover import resolve_cover_name
from ..helper.status import (
    ACHIEVEMENT_KIND,
    CARD_KINDS,
    GAME_KINDS,
    PushOptions,
    UserStatusEvent,
    is_image_mode,
    is_merge_mode,
)
from .html.game_status import (
    AchievementItem,
    AchievementRow,
    CardItem,
    GameStatusItem,
    render_game_status,
)
from .html.static_assets import get_default_avatar_url, get_img_cache_url

_TAG = "[Steam·状态推送]"
_PREFIX = "[Steam]"

_Entry = tuple[UserStatusEvent, str]
_CoverKey = tuple[str, str]
_AchievementKey = tuple[str, str]
# 一张卡与它涉及的事件；发图成功后就这些事件更新冷却
_CardGroup = tuple[CardItem, tuple[_Entry, ...]]


async def dispatch_events(events: Sequence[UserStatusEvent], *, options: PushOptions) -> None:
    """推送入口：筛选并聚合后，按推送方式组装文字或图片发送。"""
    deliveries = await collect_deliveries(events, options)
    if not deliveries:
        return
    if is_image_mode(options.mode):
        await _dispatch_image(deliveries, options)
    else:
        await _dispatch_text(deliveries, options)


async def _dispatch_text(deliveries: Sequence[Delivery], options: PushOptions) -> None:
    merge = is_merge_mode(options.mode)
    for delivery in deliveries:
        if merge:
            text = _merge_text(delivery.entries)
            await _send(delivery, text, options, _events_of(delivery.entries))
            continue
        for entry in delivery.entries:
            await _send(delivery, _single_text(entry), options, [entry[0]])


async def _dispatch_image(deliveries: Sequence[Delivery], options: PushOptions) -> None:
    split = [(delivery, _partition(delivery.entries)) for delivery in deliveries]
    card_entries = [entry for _, (cards, _) in split for entry in cards]
    if card_entries:
        covers = await _resolve_covers(card_entries, options)
        avatars = await _resolve_avatars(card_entries)
        icons = await _resolve_icons(card_entries)
    else:
        covers = {}
        avatars = {}
        icons = {}

    merge = is_merge_mode(options.mode)
    for delivery, (cards, texts) in split:
        groups = _card_groups(cards, covers, avatars, icons, options)
        if groups and merge:
            await _send_image(delivery, groups, options)
        else:
            for group in groups:
                await _send_image(delivery, [group], options)
        if not texts:
            continue
        if merge:
            await _send(delivery, _merge_text(texts), options, _events_of(texts))
            continue
        for entry in texts:
            await _send(delivery, _single_text(entry), options, [entry[0]])


def _partition(entries: Sequence[_Entry]) -> tuple[list[_Entry], list[_Entry]]:
    """拆出能出图的与只能发文字的事件；当前所有通知类型都有卡片。"""
    cards = [entry for entry in entries if entry[0].kind in CARD_KINDS]
    texts = [entry for entry in entries if entry[0].kind not in CARD_KINDS]
    return cards, texts


def _card_groups(
    cards: Sequence[_Entry],
    covers: dict[_CoverKey, str],
    avatars: dict[str, str],
    icons: dict[str, str],
    options: PushOptions,
) -> list[_CardGroup]:
    """状态事件一个事件一张卡，成就事件同一玩家同一游戏合成一张卡。"""
    achievement_entries: dict[_AchievementKey, list[_Entry]] = {}
    for entry in cards:
        event = entry[0]
        if event.kind != ACHIEVEMENT_KIND:
            continue
        key = (event.steamid64, event.appid)
        if key in achievement_entries:
            achievement_entries[key].append(entry)
        else:
            achievement_entries[key] = [entry]

    groups: list[_CardGroup] = []
    emitted: set[_AchievementKey] = set()
    for entry in cards:
        event = entry[0]
        if event.kind != ACHIEVEMENT_KIND:
            groups.append((_card_item(event, entry[1], covers, avatars, options), (entry,)))
            continue
        key = (event.steamid64, event.appid)
        if key in emitted:
            continue
        emitted.add(key)
        merged = tuple(achievement_entries[key])
        groups.append((_achievement_item(merged, avatars, icons), merged))
    return groups


async def _send_image(
    delivery: Delivery,
    groups: Sequence[_CardGroup],
    options: PushOptions,
) -> None:
    """出图并发送；渲染失败时降级为文字，避免整轮推送丢失。"""
    items = [item for item, _ in groups]
    entries = [entry for _, group in groups for entry in group]
    try:
        image = await render_game_status(items)
    except RuntimeError as error:
        logger.warning(f"{_TAG} 出图失败，降级为文字: {error!r}")
        text = _merge_text(entries) if is_merge_mode(options.mode) else _single_text(entries[0])
        await _send(delivery, text, options, _events_of(entries))
        return
    await _send(delivery, MessageSegment.image(image), options, _events_of(entries))


async def _send(
    delivery: Delivery,
    payload: str | Message,
    options: PushOptions,
    marked: Sequence[UserStatusEvent],
) -> None:
    """发一条消息；成功后对该消息涉及的事件更新推送冷却。"""
    try:
        await delivery.sub.send(payload)
    except Exception as error:
        logger.warning(f"{_TAG} 推送失败 steamid={marked[0].steamid64}: {type(error).__name__}")
        return
    for event in marked:
        cd_mark(event.steamid64, delivery.sub.group_id, options.cd_seconds)


def _single_text(entry: _Entry) -> str:
    return f"{_PREFIX} {build_message(entry[0], entry[1])}"


def _merge_text(entries: Sequence[_Entry]) -> str:
    body = "\n".join(build_message(event, name) for event, name in entries)
    return f"{_PREFIX}\n{body}"


def _events_of(entries: Sequence[_Entry]) -> list[UserStatusEvent]:
    return [event for event, _ in entries]


def _card_item(
    event: UserStatusEvent,
    name: str,
    covers: dict[_CoverKey, str],
    avatars: dict[str, str],
    options: PushOptions,
) -> GameStatusItem:
    avatar_url = get_default_avatar_url()
    if event.avatar in avatars:
        avatar_url = avatars[event.avatar]
    cover_url = ""
    cover_key = (event.appid, event.country)
    if options.with_cover and cover_key in covers:
        cover_url = covers[cover_key]
    return GameStatusItem(
        kind=event.kind,
        nickname=event.nickname or event.steamid64,
        group_name=name,
        game_name=event.game_name or event.appid,
        avatar_url=avatar_url,
        cover_url=cover_url,
    )


def _achievement_item(
    entries: Sequence[_Entry],
    avatars: dict[str, str],
    icons: dict[str, str],
) -> AchievementItem:
    """把同一玩家同一游戏的成就事件拼成一张卡，成就按事件顺序往下排。"""
    event = entries[0][0]
    avatar_url = get_default_avatar_url()
    if event.avatar in avatars:
        avatar_url = avatars[event.avatar]
    rows: list[AchievementRow] = []
    for unlock_event, _ in entries:
        unlock = unlock_event.achievement
        icon_url = icons[unlock.icon] if unlock.icon in icons else ""
        unlocked_at = unlock.time if unlock.time > 0 else unlock_event.ts
        rows.append(
            AchievementRow(
                name=unlock.name,
                description=unlock.description,
                icon_url=icon_url,
                unlocked_at=unlocked_at,
            )
        )
    return AchievementItem(
        nickname=event.nickname or event.steamid64,
        group_name=entries[0][1],
        game_name=event.game_name or event.appid,
        avatar_url=avatar_url,
        achievements=tuple(rows),
    )


async def _resolve_covers(
    entries: Sequence[_Entry], options: PushOptions
) -> dict[_CoverKey, str]:
    """开关开启时，按 (appid, 国家码) 去重解析封面直链；关闭时不做任何请求。"""
    if not options.with_cover:
        return {}
    wanted: set[_CoverKey] = set()
    for event, _ in entries:
        if event.kind in GAME_KINDS and event.appid:
            wanted.add((event.appid, event.country))
    ordered = sorted(wanted)
    results = await asyncio.gather(
        *(
            resolve_cover_name(appid, country=country, griddb_key=options.griddb_key)
            for appid, country in ordered
        ),
        return_exceptions=True,
    )
    covers: dict[_CoverKey, str] = {}
    for key, result in zip(ordered, results):
        if isinstance(result, BaseException):
            logger.warning(f"{_TAG} 封面解析失败 appid={key[0]}: {type(result).__name__}")
            continue
        if result:
            covers[key] = get_img_cache_url(result)
    return covers


async def _resolve_avatars(entries: Sequence[_Entry]) -> dict[str, str]:
    urls = [event.avatar for event, _ in entries if event.avatar]
    return await _resolve_images(urls)


async def _resolve_icons(entries: Sequence[_Entry]) -> dict[str, str]:
    urls = [
        event.achievement.icon
        for event, _ in entries
        if event.kind == ACHIEVEMENT_KIND and event.achievement.icon
    ]
    return await _resolve_images(urls)


async def _resolve_images(urls: Sequence[str]) -> dict[str, str]:
    """把外链图片落 img_cache 并换成挂载直链；失败项不进表，由调用方兜底。"""
    ordered = sorted(set(urls))
    if not ordered:
        return {}
    results = await asyncio.gather(
        *(download(url, kind="image") for url in ordered), return_exceptions=True
    )
    links: dict[str, str] = {}
    for url, result in zip(ordered, results):
        if isinstance(result, BaseException) or result is None:
            continue
        link = get_img_cache_url(result.name)
        if link:
            links[url] = link
    return links
