"""群友状态卡片：群内活跃群友的药丸列表，药丸与页脚均为公共组件。"""

from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .account_pill import PillAccount, pill_html

_CARD_WIDTH = 560
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 100
_PILL_ROW_HEIGHT = 86
_MORE_HEIGHT = 40
_FOOTER_HEIGHT = 50


def render_group_status_html(members: Sequence[PillAccount], *, has_more: bool, card_bg_url: str) -> str:
    """拼装群友状态卡片 HTML；药丸本体交给公共组件。"""
    items_html = "\n".join(pill_html(member) for member in members)
    template = get_template("steam_group_status.html")
    return template.render(
        styles=read_styles("common.css", "group_status.css"),
        bg_url=card_bg_url,
        canvas_width=_CARD_WIDTH,
        items_html=items_html,
        has_more=has_more,
        footer_html=footer_html(),
    )


async def render_group_status(members: Sequence[PillAccount], *, has_more: bool, card_bg_url: str) -> bytes:
    """渲染群友状态卡片为 JPEG 字节。"""
    html_content = render_group_status_html(members, has_more=has_more, card_bg_url=card_bg_url)
    viewport_height = _HEADER_HEIGHT + len(members) * _PILL_ROW_HEIGHT + _FOOTER_HEIGHT
    if has_more:
        viewport_height += _MORE_HEIGHT
    return await render_html(
        html_content,
        "#steam-group-status-card",
        viewport_width=_CARD_WIDTH + 40,
        viewport_height=max(viewport_height, 200),
        device_scale_factor=2.0,
    )
