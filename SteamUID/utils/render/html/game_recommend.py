"""游戏推荐卡片：标题 + 用户胶囊 + 三张横版封面卡（封面 / 名称 / 简介）+ 页脚。"""

import html
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .account_pill import PillAccount, pill_html
from .static_assets import get_font_url, get_texture_url

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

# 背景与「查看」卡片同款：压暗渐变 + bind_bg 底图
_CARD_BG_NAME = "bind_bg.jpg"
_CANVAS_WIDTH = 880
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 118
_CARD_HEIGHT = 340
_FOOTER_HEIGHT = 56


@dataclass(frozen=True)
class RecommendGame:
    """一张推荐卡：横版封面 + 游戏名 + 简介；封面缺失时留占位格。"""

    name: str
    description: str
    cover_url: str


def _game_html(game: RecommendGame) -> str:
    cover_html = ""
    if game.cover_url:
        cover_html = f'<img class="cover-img" src="{html.escape(game.cover_url)}" alt="">'
    return (
        '<div class="game-card">'
        f'<div class="cover-box">{cover_html}</div>'
        '<div class="game-info">'
        f'<div class="game-name">{html.escape(game.name)}</div>'
        f'<div class="game-desc">{html.escape(game.description)}</div>'
        "</div>"
        "</div>"
    )


def render_game_recommend_html(user: PillAccount, games: Sequence[RecommendGame]) -> str:
    """拼装游戏推荐卡片 HTML。"""
    cards = "\n".join(_game_html(game) for game in games)
    template = get_template("steam_recommend.html")
    return template.render(
        styles=read_styles("common.css", "recommend.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        canvas_width=_CANVAS_WIDTH,
        bg_url=get_texture_url(_CARD_BG_NAME),
        account_pill_html=pill_html(user),
        cards_html=cards,
        footer_html=footer_html(),
    )


async def render_game_recommend(user: PillAccount, games: Sequence[RecommendGame]) -> bytes:
    """渲染游戏推荐卡片为 JPEG 字节。"""
    if not games:
        raise ValueError("没有可推荐的游戏")

    html_content = render_game_recommend_html(user, games)
    return await render_html(
        html_content,
        "#recommend-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=_HEADER_HEIGHT + _CARD_HEIGHT + _FOOTER_HEIGHT,
        device_scale_factor=2.0,
        quality=85,
    )
