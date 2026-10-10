"""绑定列表卡片：模板拼装与统一渲染入口。"""

import html
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .static_assets import get_font_url, get_texture_url, get_default_avatar_url

_CARD_BG_NAME = "bind_bg.jpg"
_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

# 卡片高度估算：头部 + 标题 + 图例 + footer + 药丸区
_CARD_BASE_HEIGHT = 250
_PILL_ROW_HEIGHT = 86


@dataclass(frozen=True)
class BindCardItem:
    """单个账户药丸的渲染数据。"""

    name: str
    friend_code: str
    avatar_url: str
    frame_url: str
    background_url: str
    is_main: bool
    is_login: bool


def _item_html(item: BindCardItem) -> str:
    name = html.escape(item.name)
    friend_code = html.escape(item.friend_code)
    avatar_url = html.escape(item.avatar_url or get_default_avatar_url())

    dots = ""
    if item.is_main:
        dots += '<span class="status-dot main-dot"></span>'
    if item.is_login:
        dots += '<span class="status-dot login-dot"></span>'
    dots_html = f'<div class="status-dots">{dots}</div>' if dots else ""

    bg_html = ""
    if item.background_url:
        bg_url = html.escape(item.background_url)
        bg_html = f'<div class="pill-bg" style="background-image: url(\'{bg_url}\');"></div>'

    frame_html = ""
    if item.frame_url:
        frame_url = html.escape(item.frame_url)
        frame_html = f'<div class="avatar-frame"><img src="{frame_url}" alt=""></div>'

    main_class = " is-main" if item.is_main else ""
    return (
        f'<div class="pill-item{main_class}">'
        f"{bg_html}"
        f'<div class="pill-mask"></div>'
        f'<div class="pill-content">'
        f'<div class="avatar-box">'
        f'<img class="steam-avatar" src="{avatar_url}" alt="">'
        f"{frame_html}"
        f"</div>"
        f'<div class="info-box">'
        f'<div class="steam-name-row">'
        f'<div class="steam-name">{name}</div>'
        f"{dots_html}"
        f"</div>"
        f'<div class="steam-friend-code">{friend_code}</div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )


def render_bind_list_html(
    items: Sequence[BindCardItem],
    *,
    user_name: str,
    qq_avatar_url: str,
) -> str:
    """拼装绑定列表卡片 HTML，所有用户可控文本均做转义。"""
    if items:
        items_html = "\n".join(_item_html(item) for item in items)
    else:
        items_html = '<div class="empty-state">未绑定任何 Steam 账户</div>'

    template = get_template("steam_bind_list.html")
    return template.render(
        styles=read_styles("common.css", "bind_list.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        bg_url=get_texture_url(_CARD_BG_NAME),
        qq_avatar_url=qq_avatar_url or get_default_avatar_url(),
        user_name=html.escape(user_name),
        items_html=items_html,
    )


async def render_bind_list(
    items: Sequence[BindCardItem],
    *,
    user_name: str,
    qq_avatar_url: str,
) -> bytes:
    """渲染绑定列表卡片为 JPEG 字节。"""
    html_content = render_bind_list_html(items, user_name=user_name, qq_avatar_url=qq_avatar_url)
    return await render_html(
        html_content,
        "#bind-card",
        viewport_width=620,
        viewport_height=_CARD_BASE_HEIGHT + len(items) * _PILL_ROW_HEIGHT,
        device_scale_factor=2.0,
    )
