"""降价订阅卡片：标题 + 逐行封面 / 游戏名 / 当前售价 + 公共页脚。"""

import html
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .static_assets import get_bg_url
from ...helper.price import PriceKind

# 背景与「查看」卡片同款：压暗渐变 + 底图（自定义背景优先）
_CANVAS_WIDTH = 880
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 110
_ROW_HEIGHT = 62
_FOOTER_HEIGHT = 56


@dataclass(frozen=True)
class PriceEntry:
    """一行降价订阅；封面缺失时留占位格。"""

    appid: str
    name: str
    cover_url: str
    price_text: str
    price_kind: PriceKind
    discount_percent: int


@dataclass(frozen=True)
class PriceListCard:
    """降价订阅卡片数据。"""

    entries: Sequence[PriceEntry]


def _price_html(entry: PriceEntry) -> str:
    if entry.price_kind == "free":
        return '<div class="price-free">免费</div>'
    if entry.price_kind == "discount":
        return (
            f'<span class="discount-badge">-{entry.discount_percent}%</span>'
            f'<span class="price-text">{html.escape(entry.price_text)}</span>'
        )
    if entry.price_kind == "unreleased":
        return f'<div class="price-unreleased">{html.escape(entry.price_text)}</div>'
    return f'<span class="price-text">{html.escape(entry.price_text)}</span>'


def _row_html(entry: PriceEntry) -> str:
    cover_html = ""
    if entry.cover_url:
        cover_html = f'<img class="thumb" src="{html.escape(entry.cover_url)}" alt="">'
    name = html.escape(entry.name)
    return (
        '<div class="price-item">'
        '<div class="item-main">'
        '<div class="thumb-box">'
        f"{cover_html}"
        "</div>"
        '<div class="item-meta">'
        f'<div class="item-name" title="{name}">{name}</div>'
        f'<div class="item-appid">AppID: {html.escape(entry.appid)}</div>'
        "</div>"
        "</div>"
        f'<div class="col-price">{_price_html(entry)}</div>'
        "</div>"
    )


def render_price_list_html(card: PriceListCard) -> str:
    """拼装降价订阅卡片 HTML。"""
    template = get_template("steam_price_list.html")
    return template.render(
        styles=read_styles("common.css", "price_list.css"),
        canvas_width=_CANVAS_WIDTH,
        bg_url=get_bg_url(),
        title=html.escape(f"steam订阅降价 共{len(card.entries)}款"),
        items_html="\n".join(_row_html(entry) for entry in card.entries),
        footer_html=footer_html(),
    )


async def render_price_list_card(card: PriceListCard) -> bytes:
    """渲染降价订阅卡片为 JPEG 字节。"""
    if not card.entries:
        raise ValueError("没有可展示的降价订阅")

    viewport_height = _HEADER_HEIGHT + len(card.entries) * _ROW_HEIGHT + _FOOTER_HEIGHT
    return await render_html(
        render_price_list_html(card),
        "#steam-price-list-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=viewport_height,
        device_scale_factor=2.0,
        quality=85,
    )
