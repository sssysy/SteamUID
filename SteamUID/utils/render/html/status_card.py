"""steam 状态卡：迷你资料卡，静态出 JPEG，含动态素材时出 GIF。"""

import html
from dataclasses import dataclass

from .render import get_template, read_styles, render_html, render_html_gif
from .static_assets import get_default_avatar_url, get_font_url

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

_SELECTOR = "#steam-status-card"
# 容器 328px、body 放大 1.5 倍，视口按 492 宽预留
_VIEWPORT_WIDTH = 492
_VIEWPORT_HEIGHT = 600

# 动态卡帧率与时长上限，控制 GIF 体积与渲染耗时
_GIF_FPS = 10
_GIF_MAX_SECONDS = 3.0


@dataclass(frozen=True)
class StatusCard:
    """状态卡渲染数据；链接均为挂载直链，缺失为空串。"""

    name: str
    avatar_url: str
    frame_url: str
    background_url: str
    background_webm_url: str
    background_mp4_url: str
    status_text: str
    status_tone: str
    level: int
    level_border_color: str
    level_sprite_url: str
    level_offset_px: int
    badge_icon_url: str
    badge_name: str
    badge_xp: str


def _avatar_frame_html(card: StatusCard) -> str:
    """头像框叠加在头像之上；无框时不输出。"""
    if not card.frame_url:
        return ""
    return (
        '<div class="playersection_avatar_frame">'
        f'<img src="{html.escape(card.frame_url)}" alt=""></div>'
    )


def _background_html(card: StatusCard) -> str:
    """背景优先动态视频，其次静态图，都没有时留空。"""
    if card.background_webm_url or card.background_mp4_url:
        sources = ""
        if card.background_webm_url:
            src = html.escape(card.background_webm_url)
            sources += f'<source src="{src}" type="video/webm">'
        if card.background_mp4_url:
            src = html.escape(card.background_mp4_url)
            sources += f'<source src="{src}" type="video/mp4">'
        return (
            '<video class="miniprofile_nameplate" playsinline autoplay muted loop>'
            f"{sources}</video>"
        )
    if card.background_url:
        src = html.escape(card.background_url)
        return f'<img class="miniprofile_nameplate" src="{src}" alt="">'
    return ""


def _featured_badge_html(card: StatusCard) -> str:
    """特色徽章：有图标才输出，名称与经验值按有无拼接。"""
    if not card.badge_icon_url:
        return ""
    src = html.escape(card.badge_icon_url)
    name_html = ""
    if card.badge_name:
        name_html = f'<div class="name">{html.escape(card.badge_name)}</div>'
    xp_html = ""
    if card.badge_xp:
        xp_html = f'<div class="xp">{html.escape(card.badge_xp)} 点经验值</div>'
    return (
        '<div class="miniprofile_featuredcontainer">'
        f'<img class="badge_icon" src="{src}" alt="">'
        f'<div class="description">{name_html}{xp_html}</div>'
        "</div>"
    )


def _level_html(card: StatusCard) -> str:
    """等级徽章：100 级以上用官方图案精灵图，其余用段位色圆环。"""
    if card.level_sprite_url:
        src = html.escape(card.level_sprite_url)
        style = (
            f"background-image: url('{src}');"
            f" background-position: 0 {card.level_offset_px}px;"
        )
        badge_class = "friendPlayerLevel is-pattern"
    else:
        style = f"border-color: {html.escape(card.level_border_color)};"
        badge_class = "friendPlayerLevel is-ring"
    return (
        '<div class="miniprofile_featuredcontainer">'
        f'<div class="{badge_class}" style="{style}">'
        f'<span class="friendPlayerLevelNum">{card.level}</span></div>'
        '<div class="description"><div class="name">Steam 等级</div></div>'
        "</div>"
    )


def render_status_card_html(card: StatusCard) -> str:
    """拼装状态卡 HTML。"""
    template = get_template("steam_status.html")
    return template.render(
        styles=read_styles("status.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        avatar_url=html.escape(card.avatar_url or get_default_avatar_url()),
        status_tone=card.status_tone,
        border_color_class=f"border_color_{card.status_tone}",
        name=html.escape(card.name),
        status_text=html.escape(card.status_text),
        avatar_frame_html=_avatar_frame_html(card),
        background_html=_background_html(card),
        featured_badge_html=_featured_badge_html(card),
        level_html=_level_html(card),
    )


async def render_status_card(card: StatusCard, *, dynamic: bool) -> bytes:
    """出图入口：含动态素材走 GIF，否则走静态 JPEG。"""
    html_content = render_status_card_html(card)
    if dynamic:
        return await render_html_gif(
            html_content,
            _SELECTOR,
            viewport_width=_VIEWPORT_WIDTH,
            viewport_height=_VIEWPORT_HEIGHT,
            fps=_GIF_FPS,
            max_seconds=_GIF_MAX_SECONDS,
        )
    return await render_html(
        html_content,
        _SELECTOR,
        viewport_width=_VIEWPORT_WIDTH,
        viewport_height=_VIEWPORT_HEIGHT,
        device_scale_factor=2.0,
        quality=88,
    )
