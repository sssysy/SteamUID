"""降价通知卡片：封面背景 + 游戏名 / 简介 + 折扣价格块 + 公共页脚。"""

import html
from dataclasses import dataclass

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .static_assets import get_bg_url, get_font_url

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

_CANVAS_WIDTH = 880
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_VIEWPORT_HEIGHT = 470


@dataclass(frozen=True)
class PriceDropCard:
    """一张降价通知卡；discount_percent 为 0 时不出折扣块。"""

    name: str
    desc: str
    cover_url: str
    discount_percent: int
    original_price: str
    final_price: str


def _price_html(card: PriceDropCard) -> str:
    if card.discount_percent <= 0:
        return (
            '<div class="discount-block"><div class="discount-prices">'
            f'<span class="discount-final-price">{html.escape(card.final_price)}</span>'
            "</div></div>"
        )
    original = ""
    if card.original_price:
        original = f'<span class="discount-original-price">{html.escape(card.original_price)}</span>'
    return (
        '<div class="discount-block">'
        f'<div class="discount-pct">-{card.discount_percent}%</div>'
        f'<div class="discount-prices">{original}'
        f'<span class="discount-final-price">{html.escape(card.final_price)}</span>'
        "</div></div>"
    )


def render_price_drop_html(card: PriceDropCard) -> str:
    """拼装降价通知卡片 HTML。"""
    template = get_template("steam_price_drop.html")
    return template.render(
        styles=read_styles("common.css", "price_drop.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        canvas_width=_CANVAS_WIDTH,
        bg_url=get_bg_url(),
        cover_url=html.escape(card.cover_url),
        title=html.escape(card.name),
        desc_html=html.escape(card.desc) if card.desc else "暂无游戏简介",
        price_html=_price_html(card),
        footer_html=footer_html(),
    )


async def render_price_drop_card(card: PriceDropCard) -> bytes:
    """渲染降价通知卡片为 JPEG 字节。"""
    return await render_html(
        render_price_drop_html(card),
        "#steam-price-drop-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=_VIEWPORT_HEIGHT,
        device_scale_factor=2.0,
        quality=85,
    )
