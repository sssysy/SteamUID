"""绑定列表卡片：模板拼装与统一渲染入口。"""

import html
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .account_pill import PillAccount, pill_html
from .static_assets import get_font_url, get_default_avatar_url

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

# 卡片高度估算：头部 + 标题 + 图例 + footer + 药丸区
_CARD_BASE_HEIGHT = 250
_PILL_ROW_HEIGHT = 86


# 药丸本体是公共组件，绑定列表只是它的一个使用方
BindCardItem = PillAccount


def render_bind_list_html(
    items: Sequence[BindCardItem],
    *,
    user_name: str,
    qq_avatar_url: str,
    card_bg_url: str,
) -> str:
    """拼装绑定列表卡片 HTML，所有用户可控文本均做转义。"""
    if items:
        items_html = "\n".join(pill_html(item) for item in items)
    else:
        items_html = '<div class="empty-state">未绑定任何 Steam 账户</div>'

    template = get_template("steam_bind_list.html")
    return template.render(
        styles=read_styles("common.css", "bind_list.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        bg_url=card_bg_url,
        qq_avatar_url=qq_avatar_url or get_default_avatar_url(),
        user_name=html.escape(user_name),
        items_html=items_html,
        footer_html=footer_html(),
    )


async def render_bind_list(
    items: Sequence[BindCardItem],
    *,
    user_name: str,
    qq_avatar_url: str,
    card_bg_url: str,
) -> bytes:
    """渲染绑定列表卡片为 JPEG 字节。"""
    html_content = render_bind_list_html(
        items,
        user_name=user_name,
        qq_avatar_url=qq_avatar_url,
        card_bg_url=card_bg_url,
    )
    return await render_html(
        html_content,
        "#bind-card",
        viewport_width=620,
        viewport_height=_CARD_BASE_HEIGHT + len(items) * _PILL_ROW_HEIGHT,
        device_scale_factor=2.0,
    )
