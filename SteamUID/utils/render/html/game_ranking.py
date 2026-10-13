"""游戏排行榜卡片：封面 + 游戏名 + AppID + 排名 + 时长，标题右侧可挂账号胶囊。"""

import html
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .account_pill import PillAccount, pill_html
from .static_assets import get_font_url
from ...helper.ranking import format_duration

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

# 背景与「查看」卡片同款：压暗渐变 + 底图（自定义背景优先）
_CANVAS_WIDTH = 680
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 128
_ROW_HEIGHT = 58
_FOOTER_HEIGHT = 48


@dataclass(frozen=True)
class GameRankingEntry:
    """一行游戏排行；封面缺失时留占位格。"""

    appid: str
    name: str
    cover_url: str
    duration_seconds: int


def _row_html(index: int, entry: GameRankingEntry) -> str:
    cover_html = ""
    if entry.cover_url:
        cover_html = f'<img class="thumb" src="{html.escape(entry.cover_url)}" alt="">'
    name = html.escape(entry.name)
    appid = html.escape(entry.appid)
    return (
        '<div class="ranking-item">'
        '<div class="item-main">'
        '<div class="thumb-box thumb-cover">'
        f"{cover_html}"
        "</div>"
        '<div class="item-meta">'
        f'<div class="item-name" title="{name}">{name}</div>'
        f'<div class="item-appid">AppID: {appid}</div>'
        "</div>"
        "</div>"
        '<div class="item-cols">'
        f'<div class="col-rank">#{index}</div>'
        f'<div class="col-duration">{format_duration(entry.duration_seconds)}</div>'
        "</div>"
        "</div>"
    )


def render_game_ranking_html(
    title: str,
    entries: Sequence[GameRankingEntry],
    account: PillAccount | None = None,
    *,
    card_bg_url: str,
) -> str:
    """拼装游戏排行榜卡片 HTML。"""
    template = get_template("steam_game_ranking.html")
    items_html = "\n".join(_row_html(index, entry) for index, entry in enumerate(entries, 1))
    return template.render(
        styles=read_styles("common.css", "ranking.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        canvas_width=_CANVAS_WIDTH,
        bg_url=card_bg_url,
        title=html.escape(title),
        account_pill_html=pill_html(account) if account is not None else "",
        items_html=items_html,
        footer_html=footer_html(),
    )


async def render_game_ranking(
    title: str,
    entries: Sequence[GameRankingEntry],
    account: PillAccount | None = None,
    *,
    card_bg_url: str,
) -> bytes:
    """渲染游戏排行榜卡片为 JPEG 字节。"""
    html_content = render_game_ranking_html(title, entries, account, card_bg_url=card_bg_url)
    viewport_height = _HEADER_HEIGHT + len(entries) * _ROW_HEIGHT + _FOOTER_HEIGHT
    return await render_html(
        html_content,
        "#steam-ranking-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=max(viewport_height, 200),
        device_scale_factor=2.0,
    )
