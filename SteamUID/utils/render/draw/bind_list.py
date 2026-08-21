import html as html_lib
import pathlib

from ..render import (
    _fill_template,
    _get_default_icon_b64,
    _get_footer_b64,
    render_html,
)

_BIND_LIST_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "bind_list.html"


def render_bind_list_html(
    bind_items: list[dict],
    user_name: str = "",
    user_id: str = "",
    qq_avatar_url: str | None = None,
    canvas_width: int = 560,
) -> str:
    """构建 Steam 绑定列表卡片的 HTML 字符串。

    bind_items 列表项格式:
        - steamid64: str
        - name: str (Steam 昵称)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)
        - friend_code: str (Steam 好友码)
        - is_main: bool (是否为本群主账号)
    """
    template = _BIND_LIST_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_avatar = _get_default_icon_b64()

    # QQ 头像
    if not qq_avatar_url:
        uid = str(user_id)
        if uid.isdigit():
            qq_avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={uid}&s=640"
        else:
            qq_avatar_url = default_avatar

    display_user_name = html_lib.escape(user_name or user_id or "用户")

    items_html_parts = []
    if not bind_items:
        items_html = '<div class="empty-state">未绑定任何 Steam 账号</div>'
    else:
        for item in bind_items:
            name = html_lib.escape(item.get("name", "未知用户"))
            friend_code = html_lib.escape(str(item.get("friend_code", "")))
            avatar_url = item.get("avatar_url") or default_avatar
            avatar_frame_url = item.get("avatar_frame_url")
            bg_url = item.get("bg_url")
            is_main = bool(item.get("is_main", False))

            main_class = " is-main" if is_main else ""

            bg_style = f' style="background-image: url(\'{bg_url}\');"' if bg_url else ""
            bg_html = f'<div class="pill-bg"{bg_style}></div>' if bg_url else ""

            frame_html = ""
            if avatar_frame_url:
                frame_html = (
                    f'<div class="avatar-frame"><img src="{avatar_frame_url}" '
                    f'onerror="this.parentElement.style.display=\'none\'" alt=""></div>'
                )

            item_html = (
                f'<div class="pill-item{main_class}">'
                f'  {bg_html}'
                f'  <div class="pill-mask"></div>'
                f'  <div class="pill-content">'
                f'    <div class="avatar-box">'
                f'      <img class="steam-avatar" src="{avatar_url}" onerror="this.onerror=null;this.src=\'{default_avatar}\'" alt="">'
                f'      {frame_html}'
                f'    </div>'
                f'    <div class="info-box">'
                f'      <div class="steam-name" title="{name}">{name}</div>'
                f'      <div class="steam-friend-code">{friend_code}</div>'
                f'    </div>'
                f'  </div>'
                f'</div>'
            )
            items_html_parts.append(item_html)
        items_html = "\n".join(items_html_parts)

    replacements = {
        "canvas_width": str(canvas_width),
        "qq_avatar_url": qq_avatar_url,
        "default_avatar": default_avatar,
        "user_name": display_user_name,
        "items_html": items_html,
        "footer_b64": _get_footer_b64(),
    }

    return _fill_template(template, replacements)


async def render_bind_list(
    bind_items: list[dict],
    user_name: str = "",
    user_id: str = "",
    qq_avatar_url: str | None = None,
    canvas_width: int = 560,
) -> bytes:
    """渲染 Steam 绑定列表卡片为 PNG 字节。"""
    html_content = render_bind_list_html(
        bind_items=bind_items,
        user_name=user_name,
        user_id=user_id,
        qq_avatar_url=qq_avatar_url,
        canvas_width=canvas_width,
    )
    item_count = max(len(bind_items), 1)
    est_height = 140 + item_count * 86 + 60 + 35
    return await render_html(
        html_content,
        ".bind-card",
        viewport_width=canvas_width + 40,
        viewport_height=est_height,
        device_scale_factor=2.0,
    )
