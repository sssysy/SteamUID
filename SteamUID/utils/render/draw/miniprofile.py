import pathlib
from typing import Any

from ..render import _fill_template

_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "steam_miniprofile.html"

_FIELD_DEFAULTS: dict[str, Any] = {
    "avatar_url": "",  # 头像 URL
    "avatar_frame_url": None,  # 头像框 URL
    "background_video_webm": None,  # 背景视频 webm URL
    "background_video_mp4": None,  # 背景视频 mp4 URL
    "background_image_url": None,  # 背景图片 URL
    "persona_name": "",  # 个人名称
    "persona_class": "online",  # 个人状态类名
    "status_class": "online",  # 状态类名
    "status_text": "在线",  # 状态文本
    "border_color_class": "border_color_online",  # 边框颜色类名
    "level_num": "0",  # 等级
    "level_classes": "lvl_0",  # 等级类名
    "badge_icon_url": None,  # 特色徽章图标 URL
    "badge_name": None,  # 特色徽章名称
    "badge_xp": None,  # 特色徽章经验值
}


def _build_avatar_frame_html(url: str | None) -> str:
    """构建头像框 HTML 块。无头像框时返回空字符串。"""
    if not url:
        return ""
    return f'<div class="playersection_avatar_frame"><img src="{url}"></div>'


def _build_background_inner_html(
    webm: str | None,
    mp4: str | None,
    img: str | None,
) -> str:
    """构建背景内容 HTML 块。

    优先级：视频(webm/mp4) > 静态图片 > 空字符串
    """
    if webm or mp4:
        sources = ""
        if webm:
            sources += f'<source src="{webm}" type="video/webm">'
        if mp4:
            sources += f'<source src="{mp4}" type="video/mp4">'
        return (
            '<video class="miniprofile_nameplate" playsinline autoplay muted loop>'
            f"{sources}</video>"
        )
    if img:
        return f'<img class="miniprofile_nameplate" src="{img}">'
    return ""


def _build_featured_badge_html(
    icon_url: str | None,
    name: str | None,
    xp: str | None,
) -> str:
    """构建特色徽章 HTML 块。无徽章图标时返回空字符串。"""
    if not icon_url:
        return ""
    name_html = f'<div class="name">{name}</div>' if name else ""
    xp_html = f'<div class="xp">{xp} 点经验值</div>' if xp else ""
    return (
        '<div class="miniprofile_featuredcontainer">'
        f'<img src="{icon_url}" class="badge_icon">'
        f'<div class="description">{name_html}{xp_html}</div>'
        "</div>"
    )


def render_miniprofile(data: Any) -> str:
    """迷你个人资料卡片 HTML 构建"""
    # 1. 从 data 中读取所有字段
    fields = {k: getattr(data, k, v) for k, v in _FIELD_DEFAULTS.items()}

    # 2. 读取 HTML 模板
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")

    # 3. 构建条件 HTML 块
    avatar_frame_html = _build_avatar_frame_html(fields["avatar_frame_url"])
    background_inner_html = _build_background_inner_html(
        fields["background_video_webm"],
        fields["background_video_mp4"],
        fields["background_image_url"],
    )
    featured_badge_html = _build_featured_badge_html(
        fields["badge_icon_url"], fields["badge_name"], fields["badge_xp"]
    )

    # 4. 组装替换字典
    replacements: dict[str, str] = {
        "avatar_url": fields["avatar_url"],
        "persona_name": fields["persona_name"],
        "persona_class": fields["persona_class"],
        "status_class": fields["status_class"],
        "status_text": fields["status_text"],
        "border_color_class": fields["border_color_class"],
        "level_num": fields["level_num"],
        "level_classes": fields["level_classes"],
        "avatar_frame_html": avatar_frame_html,
        "background_inner_html": background_inner_html,
        "featured_badge_html": featured_badge_html,
    }

    # 5. 替换占位符并返回
    return _fill_template(template, replacements)
