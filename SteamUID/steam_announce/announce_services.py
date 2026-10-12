"""公告订阅命令的实现：订阅增删、订阅列表出图与公告轮询推送。"""

import html
from collections.abc import Sequence

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..utils.api.public import get_game_announcements
from ..utils.helper.game import GameRef, match_tip_text, resolve_game_ref
from ..utils.helper.config import region_cc, griddb_cover_key
from ..utils.helper.announce import (
    BASELINE_TASK,
    SUBSCRIBE_TASK,
    AnnounceItem,
    AnnounceBaseline,
    to_item,
    event_tag,
    baseline_of,
    announce_url,
    subscribe_ts,
    baseline_to_json,
    subscribe_fields,
    resolve_game_name,
    baseline_from_json,
    resolve_game_badge,
    is_new_announcement,
    resolve_search_cover_name,
)
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.database.model_poll import SteamPoll
from ..utils.render.html.announce_list import (
    AnnounceEntry,
    AnnounceListCard,
    render_announce_list_card,
)
from ..utils.render.html.announce_push import AnnouncePushCard, render_announce_push_card
from ..utils.render.html.static_assets import get_img_cache_url, get_default_avatar_url
from ..utils.render.html.announce_content import build_content_html

_TAG = "[Steam·公告订阅]"
_LANG = "schinese"
_WRITE_USAGE = "steam订阅公告 异环 或 steam取消订阅公告 4508340"
_NO_ANNOUNCE = "拉取不到该游戏的公告，请确认游戏名或 AppID"
_NO_SUBSCRIBE = "您当前没有订阅任何游戏公告"


def _griddb_key() -> str:
    """总开关关闭时不给 GridDB 传 key，等价于不查询。"""
    return griddb_cover_key()


def _subscribe_rows(rows: object) -> list[Subscribe]:
    """框架订阅接口无类型标注，这里立刻收窄为 Subscribe。"""
    if not isinstance(rows, Sequence):
        return []
    return [row for row in rows if isinstance(row, Subscribe)]


def _appids_of(rows: Sequence[Subscribe]) -> list[str]:
    """订阅行去重后的 appid 列表，保持首次出现顺序。"""
    appids: list[str] = []
    for row in rows:
        if row.uid and row.uid not in appids:
            appids.append(row.uid)
    return appids


def _subscribers_by_appid(rows: Sequence[Subscribe]) -> dict[str, list[Subscribe]]:
    """按 appid 聚合订阅行，推送时逐个会话发送。"""
    grouped: dict[str, list[Subscribe]] = {}
    for row in rows:
        if not row.uid:
            continue
        grouped.setdefault(row.uid, []).append(row)
    return grouped


def _name_of(rows: Sequence[Subscribe], appid: str) -> str:
    """订阅行里记下的游戏名；没有记录时回落 appid。"""
    for row in rows:
        if row.uid == appid and row.extra_message:
            return row.extra_message
    return appid


def _ts_of(rows: Sequence[Subscribe], appid: str) -> int:
    for row in rows:
        if row.uid == appid:
            return subscribe_ts(row.extra_data)
    return 0


async def _my_rows(ev: Event, appid: str) -> list[Subscribe]:
    """当前会话本人对该 appid 的订阅行。"""
    rows = await gs_subscribe.get_subscribe(
        SUBSCRIBE_TASK,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        uid=appid,
    )
    return _subscribe_rows(rows)


async def _latest(appid: str) -> AnnounceItem | None:
    """取该游戏最新一条公告；一条都没有时返回 None。"""
    events = await get_game_announcements(appid, lang=_LANG, count=1)
    if not events:
        return None
    return to_item(appid, events[0])


async def _resolve_ref(bot: Bot, ev: Event) -> GameRef:
    """解析目标游戏；走了商店搜索时先回执可能命中的结果。"""
    raw = ev.text.strip()
    if not raw:
        raise ValueError(f"请输入游戏名或 AppID，例如：{_WRITE_USAGE}")

    ref = await resolve_game_ref(raw, cc=region_cc())
    if not raw.isdigit():
        await bot.send(match_tip_text(ref))
    return ref


async def _build_card(item: AnnounceItem) -> AnnouncePushCard:
    """公告出卡：徽标与正文各自解析，正文为空时回落标题。"""
    name, cover_name = await resolve_game_badge(item.appid, cc=region_cc(), griddb_key=_griddb_key())
    content_html = await build_content_html(item.raw_body)
    if not content_html.strip():
        content_html = f"<p>{html.escape(item.title)}</p>" if item.title else "<p>暂无正文内容</p>"
    return AnnouncePushCard(
        event_tag=event_tag(item),
        title=item.title if item.title else "游戏公告",
        game_name=name,
        game_logo_url=get_img_cache_url(cover_name) if cover_name else get_default_avatar_url(),
        content_html=content_html,
    )


async def subscribe_announce(bot: Bot, ev: Event) -> None:
    """steam订阅公告<游戏名/AppID>：订阅该游戏的新公告推送。"""
    ref = await _resolve_ref(bot, ev)
    mine = await _my_rows(ev, ref.appid)
    if mine:
        await bot.send(f"该游戏已在订阅中：{_name_of(mine, ref.appid)}({ref.appid})")
        return

    # 订阅前先记下当前最新公告作为基线，避免刚订阅就把旧公告推出去
    latest = await _latest(ref.appid)
    if latest is None:
        raise ValueError(_NO_ANNOUNCE)

    name = await resolve_game_name(ref.appid, cc=region_cc())
    extra_message, extra_data = subscribe_fields(name)
    await gs_subscribe.add_subscribe(
        "single",
        SUBSCRIBE_TASK,
        ev,
        extra_message=extra_message,
        uid=ref.appid,
        extra_data=extra_data,
    )
    await SteamPoll.upsert(BASELINE_TASK, ref.appid, baseline_to_json(baseline_of(latest)))
    await bot.send(f"已订阅【{name}】({ref.appid}) 的游戏公告，有新公告时会推送给您")


async def unsubscribe_announce(bot: Bot, ev: Event) -> None:
    """steam取消订阅公告<游戏名/AppID>：取消订阅该游戏的公告推送。"""
    ref = await _resolve_ref(bot, ev)
    mine = await _my_rows(ev, ref.appid)
    if not mine:
        await bot.send(f"该游戏不在订阅中：{ref.name}({ref.appid})")
        return

    await gs_subscribe.delete_subscribe("single", SUBSCRIBE_TASK, ev, uid=ref.appid)
    # 最后一个订阅者退订后连基线一起清掉，避免轮询表留下孤儿行
    remaining = _subscribe_rows(await gs_subscribe.get_subscribe(SUBSCRIBE_TASK, uid=ref.appid))
    if not remaining:
        await SteamPoll.delete_row(BASELINE_TASK, ref.appid)
    await bot.send(f"已取消订阅【{_name_of(mine, ref.appid)}】({ref.appid}) 的公告推送")


async def build_announce_list_card(ev: Event) -> bytes:
    """steam订阅公告列表：本会话本人订阅的游戏公告渲染成卡片。"""
    rows = _subscribe_rows(
        await gs_subscribe.get_subscribe(
            SUBSCRIBE_TASK,
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
        )
    )
    appids = _appids_of(rows)
    if not appids:
        raise ValueError(_NO_SUBSCRIBE)

    cc = region_cc()
    covers = await resolve_cover_names(appids, country=cc, griddb_key=_griddb_key())
    entries: list[AnnounceEntry] = []
    for appid in appids:
        name = _name_of(rows, appid)
        cover_url = get_img_cache_url(covers[appid]) if appid in covers else ""
        if not cover_url:
            # 商店未收录的游戏官方封面必然取不到，退回商店搜索的胶囊图
            search_name, cover_name = await resolve_search_cover_name(appid, cc=cc)
            if name == appid and search_name != appid:
                name = search_name
            cover_url = get_img_cache_url(cover_name) if cover_name else ""
        entries.append(
            AnnounceEntry(
                appid=appid,
                name=name,
                cover_url=cover_url,
                subscribe_ts=_ts_of(rows, appid),
            )
        )
    return await render_announce_list_card(AnnounceListCard(entries=entries))


async def _push_announce(appid: str, item: AnnounceItem, subs: Sequence[Subscribe]) -> None:
    """向该游戏的全部订阅者推送公告卡；单个会话失败只记日志、不打断其余。"""
    card = await _build_card(item)
    image = await render_announce_push_card(card)
    for sub in subs:
        message = [
            MessageSegment.at(sub.user_id),
            MessageSegment.text(f"\n[Steam 公告订阅] {card.game_name} 发布了新公告\n"),
            MessageSegment.image(image),
            MessageSegment.text(f"公告链接：{announce_url(appid, item.gid)}"),
        ]
        try:
            await sub.send(message)
        except Exception as error:
            logger.warning(f"{_TAG} 推送失败 appid={appid} user={sub.user_id}: {type(error).__name__}")


async def _load_baselines() -> dict[str, AnnounceBaseline]:
    """一次取回全部公告基线；任务名下每行一个 appid。"""
    baselines: dict[str, AnnounceBaseline] = {}
    for row in await SteamPoll.get_all(BASELINE_TASK):
        baselines[row.key] = baseline_from_json(row.value)
    return baselines


async def _prune_baselines(appids: set[str], baselines: dict[str, AnnounceBaseline]) -> None:
    """清理已退订游戏的基线，避免表随历史订阅无限增长。"""
    for appid in baselines:
        if appid not in appids:
            await SteamPoll.delete_row(BASELINE_TASK, appid)


async def _poll_once() -> None:
    subs_by_appid = _subscribers_by_appid(_subscribe_rows(await gs_subscribe.get_subscribe(SUBSCRIBE_TASK)))
    baselines = await _load_baselines()
    await _prune_baselines(set(subs_by_appid), baselines)
    if not subs_by_appid:
        return

    for appid in sorted(subs_by_appid):
        latest = await _latest(appid)
        if latest is None:
            continue
        current = baseline_of(latest)
        previous = baselines[appid] if appid in baselines else None
        # 首轮只记基线不推送，之后 gid 变化才算新公告
        if is_new_announcement(previous, current):
            await _push_announce(appid, latest, subs_by_appid[appid])
        if previous is None or previous != current:
            await SteamPoll.upsert(BASELINE_TASK, appid, baseline_to_json(current))


async def poll_announce_once() -> None:
    """单轮公告轮询；异常在此收口，避免打断调度器。"""
    try:
        await _poll_once()
    except httpx.HTTPStatusError as error:
        logger.warning(f"{_TAG} 接口请求失败: HTTP {error.response.status_code}")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 网络请求失败: {type(error).__name__}")
    except Exception as error:
        logger.exception(f"{_TAG} 轮询异常: {type(error).__name__}")
