"""公告订阅列表卡片：标题 + 逐行封面 / 游戏名 / AppID / 订阅日期 + 公共页脚。"""

import html
import datetime
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .static_assets import FONT_NAME, get_bg_url, get_font_url

# 背景与「查看」卡片同款：压暗渐变 + 底图（自定义背景优先）
_CANVAS_WIDTH = 880
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 110
_ROW_HEIGHT = 62
_FOOTER_HEIGHT = 56

_NO_DATE = "--"


@dataclass(frozen=True)
class AnnounceEntry:
    """一行公告订阅；封面缺失时留占位格，subscribe_ts 为 0 表示没有订阅时间。"""

    appid: str
    name: str
    cover_url: str
    subscribe_ts: int


@dataclass(frozen=True)
class AnnounceListCard:
    """公告订阅列表卡片数据。"""

    entries: Sequence[AnnounceEntry]


def _subscribe_date(subscribe_ts: int) -> str:
    """订阅时间戳转 YYYY-MM-DD；没有时间戳回落占位符。"""
    if subscribe_ts <= 0:
        return _NO_DATE
    return datetime.date.fromtimestamp(subscribe_ts).isoformat()


def _row_html(entry: AnnounceEntry) -> str:
    cover_html = ""
    if entry.cover_url:
        cover_html = f'<img class="thumb" src="{html.escape(entry.cover_url, quote=True)}" alt="">'
    name = html.escape(entry.name)
    return (
        '<div class="announce-item">'
        '<div class="item-main">'
        '<div class="thumb-box">'
        f"{cover_html}"
        "</div>"
        '<div class="item-meta">'
        f'<div class="item-name" title="{name}">{name}</div>'
        f'<div class="item-appid">AppID: {html.escape(entry.appid)}</div>'
        "</div>"
        "</div>"
        f'<div class="col-subscribed">{_subscribe_date(entry.subscribe_ts)}</div>'
        "</div>"
    )


def render_announce_list_html(card: AnnounceListCard) -> str:
    """拼装公告订阅列表卡片 HTML。"""
    template = get_template("steam_announce_list.html")
    return template.render(
        styles=read_styles("common.css", "announce_list.css"),
        font_regular_url=get_font_url(FONT_NAME),
        font_medium_url=get_font_url(FONT_NAME),
        font_bold_url=get_font_url(FONT_NAME),
        canvas_width=_CANVAS_WIDTH,
        bg_url=get_bg_url(),
        title=html.escape(f"steam订阅公告列表 共{len(card.entries)}款"),
        items_html="\n".join(_row_html(entry) for entry in card.entries),
        footer_html=footer_html(),
    )


async def render_announce_list_card(card: AnnounceListCard) -> bytes:
    """渲染公告订阅列表卡片为 JPEG 字节。"""
    if not card.entries:
        raise ValueError("没有可展示的公告订阅")

    viewport_height = _HEADER_HEIGHT + len(card.entries) * _ROW_HEIGHT + _FOOTER_HEIGHT
    return await render_html(
        render_announce_list_html(card),
        "#steam-announce-list-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=viewport_height,
        device_scale_factor=2.0,
        quality=85,
    )
