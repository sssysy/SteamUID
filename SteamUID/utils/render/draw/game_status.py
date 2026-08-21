import pathlib

from ..render import _fill_template, _get_default_icon_b64, render_html

_GAME_STATUS_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "game_status.html"

_GS_THEMES: dict[str, dict] = {
    "start": {
        "status_bar_color": "#5cbe32",
        "persona_color": "#e1e1e1",
        "group_color": "#8f98a0",
        "subtitle_color": "#808a94",
        "subtitle": "正在玩",
        "game_name_color": "#90ba3c",
    },
    "end": {
        "status_bar_color": "#57cbde",
        "persona_color": "#57cbde",
        "group_color": "#4c91ac",
        "subtitle_color": "#808a94",
        "subtitle": "已结束游玩",
        "game_name_color": "#57cbde",
    },
}

_GS_DEFAULT_W = 460
_GS_DEFAULT_H_BG = 215
_GS_INFO_ROW_H = 84


def render_game_status_html(
    *,
    username: str,
    game_name: str,
    avatar_url: str,
    avatar_frame_url: str | None = None,
    game_background: str | None = None,
    is_playing: bool = True,
    group_name: str | None = None,
) -> str:
    """构建游戏状态（开始/结束游戏）卡片的 HTML 字符串。"""
    theme_key = "start" if is_playing else "end"
    theme = _GS_THEMES[theme_key]

    template = _GAME_STATUS_TEMPLATE_PATH.read_text(encoding="utf-8")

    if game_background:
        cover_html = f'<img class="cover-img" src="{game_background}" alt="">'
        cover_h_val = str(_GS_DEFAULT_H_BG)
    else:
        cover_html = ""
        cover_h_val = "0"

    avatar_frame_html = (
        f'<div class="avatar-frame"><img src="{avatar_frame_url}" alt=""></div>'
        if avatar_frame_url
        else ""
    )

    default_avatar = _get_default_icon_b64()
    avatar_src = avatar_url if avatar_url else default_avatar
    group_name_html = f'<span class="group-name">({group_name})</span>' if group_name else ""

    replacements = {
        "canvas_width": str(_GS_DEFAULT_W),
        "cover_height": cover_h_val,
        "cover_html": cover_html,
        "avatar_url": avatar_src,
        "avatar_frame_html": avatar_frame_html,
        "default_avatar": default_avatar,
        "status_bar_color": theme["status_bar_color"],
        "persona_color": theme["persona_color"],
        "group_color": theme["group_color"],
        "subtitle_color": theme["subtitle_color"],
        "persona_name": username,
        "group_name_html": group_name_html,
        "subtitle": theme["subtitle"],
        "game_name": game_name,
        "game_name_color": theme["game_name_color"],
    }

    return _fill_template(template, replacements)


async def render_game_status(
    *,
    username: str,
    game_name: str,
    avatar_url: str,
    avatar_frame_url: str | None = None,
    game_background: str | None = None,
    is_playing: bool = True,
    group_name: str | None = None,
) -> bytes:
    """渲染游戏开始/结束状态卡片为 PNG 字节。"""
    html_content = render_game_status_html(
        username=username,
        game_name=game_name,
        avatar_url=avatar_url,
        avatar_frame_url=avatar_frame_url,
        game_background=game_background,
        is_playing=is_playing,
        group_name=group_name,
    )
    total_h = (_GS_DEFAULT_H_BG if game_background else 0) + _GS_INFO_ROW_H + 50
    return await render_html(
        html_content,
        ".game-status-card",
        viewport_width=_GS_DEFAULT_W + 50,
        viewport_height=total_h,
        device_scale_factor=2.0,
    )
