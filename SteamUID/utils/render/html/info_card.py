"""steam 信息卡：全幅迷你资料背景 + 资料头部 + 统计栏 + 好友码 + 公共页脚。"""

import html
from dataclasses import dataclass

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .static_assets import get_bg_url, get_font_url, get_default_avatar_url
from ...helper.config import hide_id

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

# 无玩家背景图时与「查看」卡片同款的底图（自定义背景优先）
_CANVAS_WIDTH = 880
# 估高只用于给浏览器留视口，实际截图按元素高度裁切
_VIEWPORT_HEIGHT = 520

_NO_REGION = "未知"
_NO_AGE = "--"
_NO_VALUE = "--"


@dataclass(frozen=True)
class InfoCard:
    """信息卡渲染数据；链接均为挂载直链，缺失为空串。"""

    name: str
    friend_code: str
    avatar_url: str
    frame_url: str
    background_url: str
    status_text: str
    status_tone: str
    badge_icon_url: str
    summary: str
    level: int
    level_border_color: str
    level_sprite_url: str
    level_offset_px: int
    region: str
    account_age: str
    account_value: int | None
    currency: str
    playtime_hours: int
    game_count: int


def _avatar_html(card: InfoCard) -> str:
    frame_html = ""
    if card.frame_url:
        frame_html = f'<div class="avatar-frame"><img src="{html.escape(card.frame_url)}" alt=""></div>'
    avatar_url = html.escape(card.avatar_url or get_default_avatar_url())
    return f'<div class="avatar-wrap">{frame_html}<img class="avatar-img" src="{avatar_url}" alt=""></div>'


def _header_html(card: InfoCard) -> str:
    badge_html = ""
    if card.badge_icon_url:
        src = html.escape(card.badge_icon_url)
        badge_html = f'<img class="badge-icon" src="{src}" alt="">'
    summary_html = ""
    if card.summary:
        summary_html = f'<div class="persona-summary">{html.escape(card.summary)}</div>'
    return (
        '<div class="info-header">'
        f"{_avatar_html(card)}"
        '<div class="persona-box">'
        f'<div class="persona-name">{html.escape(card.name)}</div>'
        '<div class="status-row">'
        f"{badge_html}"
        f'<span class="status-text status-{card.status_tone}">'
        f"{html.escape(card.status_text)}</span>"
        "</div>"
        f"{summary_html}"
        "</div>"
        "</div>"
    )


def _level_html(card: InfoCard) -> str:
    """等级徽章：100 级以上用官方图案精灵图，其余用段位色圆环。"""
    if card.level_sprite_url:
        style = (
            f"background-image: url('{html.escape(card.level_sprite_url)}');"
            f" background-position: 0 {card.level_offset_px}px;"
        )
        return f'<div class="level-badge is-pattern" style="{style}"><span class="level-num">{card.level}</span></div>'
    style = f"border-color: {html.escape(card.level_border_color)};"
    return f'<div class="level-badge is-ring" style="{style}"><span class="level-num">{card.level}</span></div>'


def _stat_html(value: str, label: str) -> str:
    return f'<div class="stat-col"><div class="stat-num">{value}</div><div class="stat-label">{label}</div></div>'


def _stats_html(card: InfoCard) -> str:
    region = html.escape(card.region) if card.region else _NO_REGION
    age = f"{html.escape(card.account_age)}年" if card.account_age else _NO_AGE
    value = str(card.account_value) if card.account_value is not None else _NO_VALUE
    return (
        '<div class="glass stats-row">'
        f"{_level_html(card)}"
        '<div class="meta-col">'
        f'<div class="meta-item">地区: <span class="val">{region}</span></div>'
        f'<div class="meta-item">年限: <span class="val">{age}</span></div>'
        "</div>"
        f"{_stat_html(value, f'账号价值 {card.currency}')}"
        f"{_stat_html(str(card.playtime_hours), '游戏时长 h')}"
        f"{_stat_html(str(card.game_count), '游戏数量')}"
        "</div>"
    )


def _id_html(card: InfoCard) -> str:
    return (
        '<div class="glass id-row">'
        '<div class="id-label">好友码</div>'
        f'<div class="id-value">{html.escape(hide_id(card.friend_code))}</div>'
        "</div>"
    )


def render_info_card_html(card: InfoCard) -> str:
    """拼装信息卡 HTML。"""
    template = get_template("steam_info.html")
    return template.render(
        styles=read_styles("common.css", "info.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        canvas_width=_CANVAS_WIDTH,
        bg_url=card.background_url,
        card_bg_url=get_bg_url(),
        header_html=_header_html(card),
        stats_html=_stats_html(card),
        id_html=_id_html(card),
        footer_html=footer_html(),
    )


async def render_info_card(card: InfoCard) -> bytes:
    """把信息卡渲染为 JPEG 字节。"""
    return await render_html(
        render_info_card_html(card),
        "#steam-info-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=_VIEWPORT_HEIGHT,
        device_scale_factor=2.0,
        quality=88,
    )
