import html as html_lib
import pathlib

from ...utils import maybe_hide_steamid
from ..render import _fill_template, _get_default_icon_b64

_ACCOUNT_PILL_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "account_pill.html"


def render_account_pill_html(
    user_data: dict | None = None,
    default_avatar: str | None = None,
) -> str:
    """构建卡片右上角/顶部的药丸型 Steam 账号卡片 HTML 字符串。

    user_data 字典格式 (可选):
        - name: str (Steam 昵称)
        - friend_code: str (Steam 好友码)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)
    """
    if user_data is None:
        user_data = {}
    if default_avatar is None:
        default_avatar = _get_default_icon_b64()

    template = _ACCOUNT_PILL_TEMPLATE_PATH.read_text(encoding="utf-8")

    user_name = html_lib.escape(user_data.get("name", "未知用户"))
    raw_friend_code = str(user_data.get("friend_code", ""))
    friend_code = html_lib.escape(maybe_hide_steamid(raw_friend_code)) if raw_friend_code else ""
    avatar_url = user_data.get("avatar_url") or default_avatar
    avatar_frame_url = user_data.get("avatar_frame_url")
    bg_url = user_data.get("bg_url")

    bg_style = f' style="background-image: url(\'{bg_url}\');"' if bg_url else ""
    bg_html = f'<div class="pill-bg"{bg_style}></div>' if bg_url else ""

    frame_html = ""
    if avatar_frame_url:
        frame_html = (
            f'<div class="avatar-frame"><img src="{avatar_frame_url}" '
            f'onerror="this.parentElement.style.display=\'none\'" alt=""></div>'
        )

    replacements = {
        "user_name": user_name,
        "friend_code": friend_code,
        "avatar_url": avatar_url,
        "frame_html": frame_html,
        "bg_html": bg_html,
        "default_avatar": default_avatar,
    }
    return _fill_template(template, replacements)
