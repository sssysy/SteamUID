import pathlib
from typing import Any

from ..render import _fill_template, _get_footer_b64, render_html

_STEAM_INFO_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "steam_info.html"

_STEAM_INFO_FIELD_DEFAULTS: dict[str, Any] = {
    "avatar_url": "",
    "avatar_frame_url": None,
    "background_image_url": None,
    "persona_name": "",
    "status_class": "online",
    "status_text": "在线",
    "badge_icon_url": None,
    "bio_text": "",
    "level_num": "0",
    "level_classes": "lvl_0",
    "region": "未知",
    "account_age": "--",
    "account_value": "0",
    "playtime_hours": "0",
    "game_count": "0",
    "steam_id_display": "",
}


def render_steam_info_html(data: Any) -> str:
    """构建 Steam 信息卡片的 HTML 字符串。"""
    fields = {k: getattr(data, k, v) for k, v in _STEAM_INFO_FIELD_DEFAULTS.items()}
    template = _STEAM_INFO_TEMPLATE_PATH.read_text(encoding="utf-8")

    # 构建头像框 HTML
    avatar_frame_html = ""
    if fields["avatar_frame_url"]:
        avatar_frame_html = f'<div class="avatar_frame"><img src="{fields["avatar_frame_url"]}" alt=""></div>'

    # 构建徽章图标 HTML
    badge_icon_html = ""
    if fields["badge_icon_url"]:
        badge_icon_html = f'<img class="badge_icon" src="{fields["badge_icon_url"]}" alt="">'

    # 构建个人简介 HTML
    bio_html = ""
    if fields["bio_text"]:
        bio_html = f'<div class="profile_summary">{fields["bio_text"]}</div>'

    # 构建背景 HTML
    background_html = ""
    if fields["background_image_url"]:
        background_html = f'<img class="background_image" src="{fields["background_image_url"]}" alt="">'

    replacements = {
        "avatar_url": fields["avatar_url"],
        "avatar_frame_html": avatar_frame_html,
        "background_html": background_html,
        "persona_name": fields["persona_name"],
        "badge_icon_html": badge_icon_html,
        "status_class": fields["status_class"],
        "status_text": fields["status_text"],
        "bio_html": bio_html,
        "level_num": str(fields["level_num"]),
        "level_classes": fields["level_classes"],
        "region": fields["region"],
        "account_age": str(fields["account_age"]),
        "account_value": str(fields["account_value"]),
        "playtime_hours": str(fields["playtime_hours"]),
        "game_count": str(fields["game_count"]),
        "steam_id_display": str(fields["steam_id_display"]),
        "footer_b64": _get_footer_b64(),
    }

    return _fill_template(template, replacements)


async def render_steam_info(data: Any) -> bytes:
    """渲染 Steam 信息卡片为 PNG 字节。"""
    html_content = render_steam_info_html(data)
    return await render_html(
        html_content,
        ".steam_info_card",
        viewport_width=820,
        viewport_height=460,
        device_scale_factor=2.0,
    )
