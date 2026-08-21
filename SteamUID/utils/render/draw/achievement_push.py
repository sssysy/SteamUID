import html as html_lib
import pathlib

from ..render import (
    _fill_template,
    _get_default_icon_b64,
    render_html,
)
from .account_pill import render_account_pill_html

_ACHIEVEMENT_PUSH_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "achievement_push.html"


def render_achievement_push_html(
    user_data: dict,
    achievement_data: dict,
    canvas_width: int = 440,
) -> str:
    """构建 Steam 获得成就订阅推送卡片的 HTML 字符串。

    user_data 字典格式:
        - name: str (Steam 昵称)
        - friend_code: str (Steam 好友码)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)

    achievement_data 字典格式:
        - game_name: str (游戏名称)
        - name: str (成就名称)
        - description: str (成就描述)
        - icon_url: str (成就图标 URL)
    """
    template = _ACHIEVEMENT_PUSH_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_icon = _get_default_icon_b64()
    default_avatar = default_icon

    # 1. 顶部用户账号卡片
    account_pill_html = render_account_pill_html(user_data, default_avatar)

    # 2. 成就信息
    game_name = html_lib.escape(achievement_data.get("game_name", "未知游戏"))
    achievement_name = html_lib.escape(achievement_data.get("name", "无名称"))
    achievement_desc = html_lib.escape(achievement_data.get("description", "无描述"))
    achievement_icon_url = achievement_data.get("icon_url") or default_icon

    replacements = {
        "canvas_width": str(canvas_width),
        "account_pill_html": account_pill_html,
        "default_icon": default_icon,
        "game_name": game_name,
        "achievement_name": achievement_name,
        "achievement_desc": achievement_desc,
        "achievement_icon_url": achievement_icon_url,
    }

    return _fill_template(template, replacements)


async def render_achievement_push(
    user_data: dict,
    achievement_data: dict,
    canvas_width: int = 440,
) -> bytes:
    """渲染 Steam 获得成就订阅推送卡片为 PNG 字节。"""
    html_content = render_achievement_push_html(
        user_data=user_data,
        achievement_data=achievement_data,
        canvas_width=canvas_width,
    )

    return await render_html(
        html_content,
        ".achievement-push-card",
        viewport_width=canvas_width + 40,
        viewport_height=300,
        device_scale_factor=2.0,
    )
