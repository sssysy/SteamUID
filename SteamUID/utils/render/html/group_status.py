"""状态卡片：群友 / 好友的药丸列表，药丸与页脚均为公共组件。"""

from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .account_pill import PillAccount, pill_html

# 单列卡片宽度；两列时加宽，避免药丸文字被挤得过窄
_CARD_WIDTH = 560
_CARD_WIDTH_TWO_COL = 900
# 超过 15 人改两列均分，正好 15 人仍保持单列
_TWO_COLUMN_THRESHOLD = 15

# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_HEADER_HEIGHT = 100
_PILL_ROW_HEIGHT = 86
_MORE_HEIGHT = 40
_FOOTER_HEIGHT = 50


def _layout(count: int) -> tuple[int, int, int]:
    """按人数返回 (列数, 行数, 画布宽度)；两列时左右均分。"""
    if count > _TWO_COLUMN_THRESHOLD:
        return 2, (count + 1) // 2, _CARD_WIDTH_TWO_COL
    return 1, count, _CARD_WIDTH


def render_group_status_html(
    members: Sequence[PillAccount],
    *,
    title: str,
    more_text: str,
    card_bg_url: str,
) -> str:
    """拼装状态卡片 HTML；药丸本体交给公共组件。"""
    columns, rows, canvas_width = _layout(len(members))
    items_html = "\n".join(pill_html(member) for member in members)
    template = get_template("steam_group_status.html")
    return template.render(
        styles=read_styles("common.css", "group_status.css"),
        title=title,
        bg_url=card_bg_url,
        canvas_width=canvas_width,
        columns=columns,
        rows=rows,
        items_html=items_html,
        more_text=more_text,
        footer_html=footer_html(),
    )


async def render_group_status(
    members: Sequence[PillAccount],
    *,
    title: str,
    more_text: str,
    card_bg_url: str,
) -> bytes:
    """渲染状态卡片为 JPEG 字节。"""
    html_content = render_group_status_html(
        members,
        title=title,
        more_text=more_text,
        card_bg_url=card_bg_url,
    )
    _columns, rows, canvas_width = _layout(len(members))
    viewport_height = _HEADER_HEIGHT + rows * _PILL_ROW_HEIGHT + _FOOTER_HEIGHT
    if more_text:
        viewport_height += _MORE_HEIGHT
    return await render_html(
        html_content,
        "#steam-group-status-card",
        viewport_width=canvas_width + 40,
        viewport_height=max(viewport_height, 200),
        device_scale_factor=2.0,
    )
