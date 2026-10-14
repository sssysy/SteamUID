"""愿望单卡片：标题 + 账号胶囊 + 列头 + 逐行封面 / 名称 / 添加日期 / 售价 + 公共页脚。"""

import html
import datetime
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .account_pill import PillAccount, pill_html
from ...helper.price import PriceKind

# 背景与「查看」卡片同款：压暗渐变 + 底图（自定义背景优先）
_CANVAS_WIDTH = 880
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 150
_ROW_HEIGHT = 62
_FOOTER_HEIGHT = 56

_NO_DATE = "--"


@dataclass(frozen=True)
class WishlistEntry:
    """一行愿望单；封面缺失时留占位格，added_ts 为 0 表示无添加时间。"""

    appid: str
    name: str
    cover_url: str
    added_ts: int
    price_text: str
    price_kind: PriceKind
    discount_percent: int


@dataclass(frozen=True)
class WishlistCard:
    """愿望单卡片数据；hidden 为受条数限制未显示的条数。"""

    total: int
    hidden: int
    entries: Sequence[WishlistEntry]


def _added_date(added_ts: int) -> str:
    """添加时间戳转 YYYY-MM-DD；无时间戳回落占位符。"""
    if added_ts <= 0:
        return _NO_DATE
    return datetime.date.fromtimestamp(added_ts).isoformat()


def _price_html(entry: WishlistEntry) -> str:
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


def _row_html(entry: WishlistEntry) -> str:
    cover_html = ""
    if entry.cover_url:
        cover_html = f'<img class="thumb" src="{html.escape(entry.cover_url)}" alt="">'
    name = html.escape(entry.name)
    return (
        '<div class="wishlist-item">'
        '<div class="item-main">'
        '<div class="thumb-box">'
        f"{cover_html}"
        "</div>"
        '<div class="item-meta">'
        f'<div class="item-name" title="{name}">{name}</div>'
        f'<div class="item-appid">AppID: {html.escape(entry.appid)}</div>'
        "</div>"
        "</div>"
        '<div class="item-cols">'
        f'<div class="col-added">{_added_date(entry.added_ts)}</div>'
        f'<div class="col-price">{_price_html(entry)}</div>'
        "</div>"
        "</div>"
    )


def render_wishlist_html(user: PillAccount, card: WishlistCard, *, card_bg_url: str) -> str:
    """拼装愿望单卡片 HTML。"""
    rows = [_row_html(entry) for entry in card.entries]
    if card.hidden > 0:
        rows.append(f'<div class="wishlist-overflow">剩余 {card.hidden} 款愿望单游戏未显示</div>')

    template = get_template("steam_wishlist.html")
    return template.render(
        styles=read_styles("common.css", "wishlist.css"),
        canvas_width=_CANVAS_WIDTH,
        bg_url=card_bg_url,
        title=html.escape(f"steam愿望单列表 共{card.total}款"),
        account_pill_html=pill_html(user),
        items_html="\n".join(rows),
        footer_html=footer_html(),
    )


async def render_wishlist_card(user: PillAccount, card: WishlistCard, *, card_bg_url: str) -> bytes:
    """渲染愿望单卡片为 JPEG 字节。"""
    if not card.entries:
        raise ValueError("没有可展示的愿望单游戏")

    viewport_height = _HEADER_HEIGHT + len(card.entries) * _ROW_HEIGHT + _FOOTER_HEIGHT
    return await render_html(
        render_wishlist_html(user, card, card_bg_url=card_bg_url),
        "#steam-wishlist-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=viewport_height,
        device_scale_factor=2.0,
        quality=85,
    )
