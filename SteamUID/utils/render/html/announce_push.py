"""公告推送卡片：类型 / 标题 + 右上角游戏徽标 + 正文 + 公共页脚。"""

import html
from dataclasses import dataclass

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .static_assets import FONT_NAME, get_font_url

# 正文长度不可预期，视口只是起点，实际截图按元素高度裁切
_CANVAS_WIDTH = 720
_VIEWPORT_HEIGHT = 1600


@dataclass(frozen=True)
class AnnouncePushCard:
    """一张公告推送卡；event_tag 为「类型 · 发布时间」。"""

    event_tag: str
    title: str
    game_name: str
    game_logo_url: str
    content_html: str


def render_announce_push_html(card: AnnouncePushCard) -> str:
    """拼装公告推送卡片 HTML。"""
    template = get_template("steam_announce_push.html")
    return template.render(
        styles=read_styles("common.css", "announce_push.css"),
        font_regular_url=get_font_url(FONT_NAME),
        font_medium_url=get_font_url(FONT_NAME),
        font_bold_url=get_font_url(FONT_NAME),
        canvas_width=_CANVAS_WIDTH,
        event_tag=html.escape(card.event_tag),
        announce_title=html.escape(card.title),
        game_name=html.escape(card.game_name),
        game_logo_url=html.escape(card.game_logo_url, quote=True),
        content_html=card.content_html,
        footer_html=footer_html(),
    )


async def render_announce_push_card(card: AnnouncePushCard) -> bytes:
    """渲染公告推送卡片为 JPEG 字节。"""
    return await render_html(
        render_announce_push_html(card),
        "#steam-announce-push-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=_VIEWPORT_HEIGHT,
        device_scale_factor=2.0,
        quality=85,
    )
