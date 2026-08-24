import html as html_lib
import pathlib

from ..render import (
    _fill_template,
    _get_default_icon_b64,
    render_html,
)

_STATUS_TEMPLATE_PATH = (
    pathlib.Path(__file__).parent.parent / "html" / "group_member_status.html"
)


def render_group_member_status_html(
    member_data_list: list[dict],
    has_more: bool = False,
    title_text: str = "steam群友状态",
    canvas_width: int = 560,
) -> str:
    """构建 Steam 群友状态卡片的 HTML 字符串。

    member_data_list item 字典格式:
        - user_name: str (用户 QQ / 群昵称)
        - avatar_url: str | None (QQ 头像 URL)
        - status: str ("ingame" | "online")
        - status_text: str (如 "游戏中：Counter-Strike 2" 或 "在线")
        - bg_url: str | None (游戏封面横幅或迷你资料背景 URL)
    """
    template = _STATUS_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_avatar = _get_default_icon_b64()

    items_html_parts = []
    for item in member_data_list:
        user_name = html_lib.escape(item.get("user_name") or "未知用户")
        avatar_url = item.get("avatar_url") or default_avatar
        status = item.get("status", "online")
        status_text = html_lib.escape(item.get("status_text") or "在线")
        bg_url = item.get("bg_url")

        bg_style = f' style="background-image: url(\'{bg_url}\');"' if bg_url else ""
        bg_html = f'<div class="pill-bg"{bg_style}></div>' if bg_url else ""

        status_class = "ingame" if status == "ingame" else "online"

        pill_html = (
            f'<div class="pill-item">\n'
            f'  {bg_html}\n'
            f'  <div class="pill-mask"></div>\n'
            f'  <div class="pill-content">\n'
            f'    <div class="avatar-box">\n'
            f'      <img class="qq-avatar" src="{avatar_url}" onerror="this.onerror=null;this.src=\'{default_avatar}\'" alt="">\n'
            f'    </div>\n'
            f'    <div class="info-box">\n'
            f'      <div class="user-name" title="{user_name}">{user_name}</div>\n'
            f'      <div class="status-text {status_class}">{status_text}</div>\n'
            f'    </div>\n'
            f'  </div>\n'
            f'</div>'
        )
        items_html_parts.append(pill_html)

    items_html = "\n".join(items_html_parts)
    more_dots_html = '<div class="more-dots">...</div>' if has_more else ""

    replacements = {
        "canvas_width": str(canvas_width),
        "title_text": html_lib.escape(title_text),
        "items_html": items_html,
        "more_dots_html": more_dots_html,
    }

    return _fill_template(template, replacements)


async def render_group_member_status(
    member_data_list: list[dict],
    has_more: bool = False,
    title_text: str = "steam群友状态",
    canvas_width: int = 560,
) -> bytes:
    """渲染 Steam 群友状态卡片为 PNG 字节。"""
    html_content = render_group_member_status_html(
        member_data_list=member_data_list,
        has_more=has_more,
        title_text=title_text,
        canvas_width=canvas_width,
    )
    item_count = max(len(member_data_list), 1)
    est_height = 80 + item_count * 86 + (40 if has_more else 0) + 50 + 35
    return await render_html(
        html_content,
        ".status-container",
        viewport_width=canvas_width + 40,
        viewport_height=max(est_height, 200),
        device_scale_factor=2.0,
    )
