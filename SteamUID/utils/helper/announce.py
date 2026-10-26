"""公告订阅的领域逻辑：订阅任务名、公告基线编解码、事件类型文案与卡片字段解析。

只碰 api 与缓存，卡片拼装与渲染交给 render 层。
"""

import time
import datetime
from typing import TypedDict
from dataclasses import dataclass

import msgspec

from .game_cover import resolve_cover_name, download_image_name
from ..api.models import StoreEvent
from .game_detail import pics_game_meta, resolve_game_name, preferred_game_name

_TAG = "[Steam·公告订阅]"
_LANG = "schinese"

# 订阅行 uid 存 appid，列表与轮询都从这里取集合
SUBSCRIBE_TASK = "订阅Steam公告"
# 公告基线与轮询集合同表：任务名「公告轮询」下每行一个 appid
BASELINE_TASK = "公告轮询"

_NEWS_BASE = "https://store.steampowered.com/news/app"

# Steam 官方事件类型
EVENT_TYPE_NAMES: dict[int, str] = {
    1: "社区活动",
    2: "游戏活动",
    3: "派对活动",
    4: "会议活动",
    5: "特别活动",
    6: "音乐与艺术",
    7: "体育活动",
    8: "出行活动",
    9: "聊天活动",
    10: "游戏发售",
    11: "直播活动",
    12: "补丁更新",
    13: "重大更新预告",
    14: "重大更新",
    15: "DLC 发售",
    16: "即将推出",
    17: "电竞赛事",
    18: "开发者直播",
    19: "特邀直播",
    20: "促销特惠",
    21: "道具特惠",
    22: "双倍经验",
    23: "掉落活动",
    24: "特权活动",
    25: "游戏挑战",
    26: "游戏比赛",
    27: "线下活动",
    28: "新闻公告",
    29: "测试版发布",
    30: "游戏内容更新",
    31: "免费试玩",
    32: "赛季发布",
    33: "赛季更新",
    34: "交叉推广",
    35: "游戏内活动",
}

_UNKNOWN_TYPE = "官方公告"


class AnnounceBaseline(TypedDict, total=False):
    """公告基线：只记最新一条的 gid 与发布时间。"""

    gid: str
    posttime: int


@dataclass(frozen=True)
class AnnounceItem:
    """一条公告整理后的卡片数据：标题、类型文案、发布时间与正文 BBCode。"""

    appid: str
    gid: str
    title: str
    type_name: str
    posttime: int
    raw_body: str


def to_item(appid: str, event: StoreEvent) -> AnnounceItem:
    """整理公告事件；标题优先事件名，缺失时回落正文标题。"""
    body = event["announcement_body"] if "announcement_body" in event else None
    headline = body["headline"] if body is not None and "headline" in body else ""
    raw_body = body["body"] if body is not None and "body" in body else ""
    posttime = body["posttime"] if body is not None and "posttime" in body else 0
    event_name = event["event_name"] if "event_name" in event else ""
    event_type = event["event_type"] if "event_type" in event else 0
    return AnnounceItem(
        appid=appid,
        gid=event["gid"] if "gid" in event else "",
        title=event_name if event_name else headline,
        type_name=EVENT_TYPE_NAMES[event_type] if event_type in EVENT_TYPE_NAMES else _UNKNOWN_TYPE,
        posttime=posttime,
        raw_body=raw_body,
    )


def event_tag(item: AnnounceItem) -> str:
    """卡片角标：类型 + 本地发布时间，没有时间时只剩类型。"""
    if item.posttime <= 0:
        return item.type_name
    stamp = datetime.datetime.fromtimestamp(item.posttime).strftime("%Y-%m-%d %H:%M")
    return f"{item.type_name} · {stamp}"


def announce_url(appid: str, gid: str) -> str:
    """公告网页地址；gid 缺失时退回该游戏的公告列表页。"""
    if not gid:
        return f"{_NEWS_BASE}/{appid}"
    return f"{_NEWS_BASE}/{appid}/view/{gid}?l={_LANG}"


def baseline_of(item: AnnounceItem) -> AnnounceBaseline:
    """从整理后的公告取基线。"""
    return AnnounceBaseline(gid=item.gid, posttime=item.posttime)


def baseline_to_json(baseline: AnnounceBaseline) -> str:
    return msgspec.json.encode(baseline).decode()


def baseline_from_json(raw: str) -> AnnounceBaseline:
    """解析基线 JSON；结构非法时抛 msgspec.ValidationError。"""
    return msgspec.json.decode(raw, type=AnnounceBaseline)


def is_new_announcement(previous: AnnounceBaseline | None, current: AnnounceBaseline) -> bool:
    """是否需要推送：没有基线说明是首轮，只记基线不推送；gid 变化才算新公告。"""
    if previous is None:
        return False
    if "gid" not in previous or "gid" not in current:
        return False
    return current["gid"] != previous["gid"]


def subscribe_fields(name: str) -> tuple[str, str]:
    """订阅行的附加字段：extra_message 存游戏名，extra_data 存订阅时间戳。"""
    return name, msgspec.json.encode({"ts": int(time.time())}).decode()


def subscribe_ts(extra_data: str | None) -> int:
    """取订阅时间戳；没有记录或没有 ts 字段时返回 0。"""
    if not extra_data:
        return 0
    payload: dict[str, int] = msgspec.json.decode(extra_data, type=dict[str, int])
    return payload["ts"] if "ts" in payload else 0


async def resolve_game_badge(appid: str, *, cc: str, lang: str, griddb_key: str) -> tuple[str, str]:
    """卡片顶部的游戏名与方形 logo 文件名：PICS 方形图标优先，取不到回落官方封面。"""
    name = await resolve_game_name(appid, cc=cc, lang=lang) or appid
    name = await preferred_game_name(appid, fallback=name, lang=lang)
    meta = await pics_game_meta(appid, lang=lang)
    icon = await download_image_name(meta["icon_url"]) if "icon_url" in meta else ""
    if icon:
        return name, icon
    return name, await resolve_cover_name(appid, country=cc, lang=lang, griddb_key=griddb_key)
