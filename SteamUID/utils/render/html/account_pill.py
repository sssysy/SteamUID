"""账号胶囊组件：绑定列表与游戏墙共用的同一款药丸。

样式固定在 common.css 的 .pill-item 段，使用方只允许覆盖外层宽度，
新增卡片一律复用本模块，禁止再各抄一份 HTML 或 CSS。
"""

import html
from dataclasses import dataclass

from .static_assets import get_default_avatar_url


@dataclass(frozen=True)
class PillAccount:
    """一个账号胶囊的渲染数据；图片与背景均为挂载直链。"""

    name: str
    friend_code: str
    avatar_url: str
    frame_url: str
    background_url: str
    is_main: bool = False
    is_login: bool = False


def pill_html(account: PillAccount) -> str:
    """拼装药丸 HTML；is_main / is_login 决定名字右侧的状态点。"""
    avatar_url = html.escape(account.avatar_url or get_default_avatar_url())

    bg_html = ""
    if account.background_url:
        bg_url = html.escape(account.background_url)
        bg_html = f'<div class="pill-bg" style="background-image: url(\'{bg_url}\');"></div>'

    frame_html = ""
    if account.frame_url:
        frame_url = html.escape(account.frame_url)
        frame_html = f'<div class="avatar-frame"><img src="{frame_url}" alt=""></div>'

    dots = ""
    if account.is_main:
        dots += '<span class="status-dot main-dot"></span>'
    if account.is_login:
        dots += '<span class="status-dot login-dot"></span>'
    dots_html = f'<div class="status-dots">{dots}</div>' if dots else ""

    main_class = " is-main" if account.is_main else ""
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
        f'<div class="steam-name">{html.escape(account.name)}</div>'
        f"{dots_html}"
        f"</div>"
        f'<div class="steam-friend-code">{html.escape(account.friend_code)}</div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )
