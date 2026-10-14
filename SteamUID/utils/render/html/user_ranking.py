"""群玩家排行榜卡片：头像 + 群名片 + 排名 + 时长，标题右侧可挂游戏徽标。"""

import html
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .static_assets import FONT_NAME, get_font_url, get_default_avatar_url
from ...helper.ranking import format_duration

# 背景与「查看」卡片同款：压暗渐变 + 底图（自定义背景优先）
_CANVAS_WIDTH = 680
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 128
_ROW_HEIGHT = 58
_FOOTER_HEIGHT = 48


@dataclass(frozen=True)
class UserRankingEntry:
    """一行玩家排行；头像缺失时模板侧回落默认头像。"""

    name: str
    avatar_url: str
    duration_seconds: int


@dataclass(frozen=True)
class RankingBadge:
    """标题右侧的游戏徽标；logo 缺失时只显示游戏名。"""

    name: str
    logo_url: str


def _row_html(index: int, entry: UserRankingEntry) -> str:
    avatar_url = html.escape(entry.avatar_url or get_default_avatar_url())
    name = html.escape(entry.name)
    return (
        '<div class="ranking-item">'
        '<div class="item-main">'
        '<div class="thumb-box">'
        f'<img class="thumb" src="{avatar_url}" alt="">'
        "</div>"
        f'<div class="item-name" title="{name}">{name}</div>'
        "</div>"
        '<div class="item-cols">'
        f'<div class="col-rank">#{index}</div>'
        f'<div class="col-duration">{format_duration(entry.duration_seconds)}</div>'
        "</div>"
        "</div>"
    )


def _badge_html(badge: RankingBadge | None) -> str:
    if badge is None:
        return ""
    logo_html = ""
    if badge.logo_url:
        logo_html = f'<img class="badge-logo" src="{html.escape(badge.logo_url)}" alt="">'
    name = html.escape(badge.name)
    return f'<div class="game-badge">{logo_html}<div class="badge-name" title="{name}">{name}</div></div>'


def render_user_ranking_html(
    title: str,
    entries: Sequence[UserRankingEntry],
    badge: RankingBadge | None = None,
    *,
    card_bg_url: str,
) -> str:
    """拼装玩家排行榜卡片 HTML。"""
    template = get_template("steam_user_ranking.html")
    items_html = "\n".join(_row_html(index, entry) for index, entry in enumerate(entries, 1))
    return template.render(
        styles=read_styles("common.css", "ranking.css"),
        font_regular_url=get_font_url(FONT_NAME),
        font_medium_url=get_font_url(FONT_NAME),
        font_bold_url=get_font_url(FONT_NAME),
        canvas_width=_CANVAS_WIDTH,
        bg_url=card_bg_url,
        title=html.escape(title),
        badge_html=_badge_html(badge),
        items_html=items_html,
        footer_html=footer_html(),
    )


async def render_user_ranking(
    title: str,
    entries: Sequence[UserRankingEntry],
    badge: RankingBadge | None = None,
    *,
    card_bg_url: str,
) -> bytes:
    """渲染玩家排行榜卡片为 JPEG 字节。"""
    html_content = render_user_ranking_html(title, entries, badge, card_bg_url=card_bg_url)
    viewport_height = _HEADER_HEIGHT + len(entries) * _ROW_HEIGHT + _FOOTER_HEIGHT
    return await render_html(
        html_content,
        "#steam-ranking-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=max(viewport_height, 200),
        device_scale_factor=2.0,
    )
