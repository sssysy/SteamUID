"""Steam 榜单卡片：标题 + 副标题 + 3×3 封面宫格 + 页脚。

宫格顺序即榜单名次顺序，名次角标直接取 Steam 真实名次，不按宫格重排。
"""

import html
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .static_assets import FONT_NAME, get_font_url

# 背景与「查看」卡片同款：压暗渐变 + 底图（自定义背景优先）
_CANVAS_WIDTH = 880
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 120
_GRID_HEIGHT = 1080
_FOOTER_HEIGHT = 56


@dataclass(frozen=True)
class ChartPrice:
    """价格行：免费 / 折扣 / 标价三态；discount_percent 为 0 时不显示划线价。"""

    is_free: bool
    price_text: str
    original_text: str
    discount_percent: int


@dataclass(frozen=True)
class ChartPlayers:
    """在线人数行：当前在线 / 历史峰值。"""

    concurrent: int
    peak: int


@dataclass(frozen=True)
class ChartRank:
    """周活跃行：峰值 + 相对上周的名次升降，正为上升、负为下降、0 持平。"""

    peak: int
    delta: int


@dataclass(frozen=True)
class ChartGame:
    """一格榜单；三行数值按榜单类型取其中一种。"""

    rank: int
    name: str
    description: str
    cover_url: str
    value: ChartPrice | ChartPlayers | ChartRank


# 三种榜单数值行共用同一字段类型
ChartValue = ChartPrice | ChartPlayers | ChartRank


def _rank_class(rank: int) -> str:
    """前三名换金银铜配色，其余用默认灰。"""
    return f" rank-{rank}" if rank <= 3 else ""


def _value_html(value: ChartValue) -> str:
    if isinstance(value, ChartPrice):
        if value.is_free:
            return '<div class="value-row"><span class="price-free">免费开玩</span></div>'
        if not value.price_text:
            return '<div class="value-row"><span class="price-none">暂无定价</span></div>'
        price = html.escape(value.price_text)
        if value.discount_percent > 0 and value.original_text:
            return (
                '<div class="value-row">'
                f'<span class="discount-badge">-{value.discount_percent}%</span>'
                f'<span class="price-original">{html.escape(value.original_text)}</span>'
                f'<span class="price-final">{price}</span>'
                "</div>"
            )
        return f'<div class="value-row"><span class="price-final">{price}</span></div>'

    if isinstance(value, ChartPlayers):
        return (
            '<div class="value-row">'
            f'<span class="value-main">{value.concurrent:,}</span>'
            '<span class="value-sep">/</span>'
            f'<span class="value-sub">{value.peak:,}</span>'
            "</div>"
        )

    if value.delta > 0:
        delta_html = f'<span class="value-up">↑{value.delta}</span>'
    elif value.delta < 0:
        delta_html = f'<span class="value-down">↓{-value.delta}</span>'
    else:
        delta_html = '<span class="value-flat">—</span>'
    return f'<div class="value-row"><span class="value-main">{value.peak:,}</span>{delta_html}</div>'


def _cell_html(game: ChartGame) -> str:
    cover_html = ""
    if game.cover_url:
        cover_html = f'<img class="cover-img" src="{html.escape(game.cover_url)}" alt="">'
    name = html.escape(game.name)
    return (
        '<div class="game-cell">'
        '<div class="cover-box">'
        f"{cover_html}"
        f'<div class="rank-badge{_rank_class(game.rank)}">{game.rank}</div>'
        "</div>"
        '<div class="cell-info">'
        f'<div class="game-name" title="{name}">{name}</div>'
        f'<div class="game-desc">{html.escape(game.description)}</div>'
        f"{_value_html(game.value)}"
        "</div>"
        "</div>"
    )


def render_steam_charts_html(
    title: str,
    subtitle: str,
    games: Sequence[ChartGame],
    *,
    card_bg_url: str,
) -> str:
    """拼装榜单宫格卡片 HTML。"""
    template = get_template("steam_charts.html")
    cells = "\n".join(_cell_html(game) for game in games)
    return template.render(
        styles=read_styles("common.css", "charts.css"),
        font_regular_url=get_font_url(FONT_NAME),
        font_medium_url=get_font_url(FONT_NAME),
        font_bold_url=get_font_url(FONT_NAME),
        canvas_width=_CANVAS_WIDTH,
        bg_url=card_bg_url,
        title=html.escape(title),
        subtitle=html.escape(subtitle),
        cells_html=cells,
        footer_html=footer_html(),
    )


async def render_steam_charts(
    title: str,
    subtitle: str,
    games: Sequence[ChartGame],
    *,
    card_bg_url: str,
) -> bytes:
    """渲染榜单宫格卡片为 JPEG 字节。"""
    if not games:
        raise ValueError("没有可渲染的榜单数据")

    html_content = render_steam_charts_html(title, subtitle, games, card_bg_url=card_bg_url)
    return await render_html(
        html_content,
        "#steam-charts-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=_HEADER_HEIGHT + _GRID_HEIGHT + _FOOTER_HEIGHT,
        device_scale_factor=2.0,
    )
