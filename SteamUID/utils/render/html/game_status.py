"""状态卡与成就卡：支持 1~N 张一次出图，多张横向换行排列。"""

import html
import time
from dataclasses import dataclass
from collections.abc import Sequence

from .render import get_template, read_styles, render_html
from .static_assets import get_font_url, get_bg_url
from ...helper.status import ACHIEVEMENT_KIND, GAME_KINDS

_CARD_WIDTH = 460
_COVER_HEIGHT = 215
_ROW_HEIGHT = 84
_MAX_COLUMNS = 5

# 成就卡背景与「查看」卡片同款：压暗渐变 + 底图（自定义背景优先）

# 成就卡估高参数：头部之外每条成就占一行，列表底部留一点内边距
_ACHIEVEMENT_ROW_HEIGHT = 74
_ACHIEVEMENT_LIST_PADDING = 12
# 单卡最多铺几条成就，超出折叠成一行汇总
_MAX_ACHIEVEMENT_ROWS = 5
_ACHIEVEMENT_MORE_HEIGHT = 30

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class GameStatusItem:
    """单张状态卡的渲染数据；群名与游戏名已由上层补全。"""

    kind: str
    nickname: str
    group_name: str
    game_name: str
    avatar_url: str
    cover_url: str = ""


@dataclass(frozen=True)
class AchievementRow:
    """一条成就：图标直链、名称、介绍与解锁时间戳。"""

    name: str
    description: str
    icon_url: str
    unlocked_at: int


@dataclass(frozen=True)
class AchievementItem:
    """单张成就卡：同一玩家同一游戏本轮解锁的成就，按顺序往下拼。"""

    nickname: str
    group_name: str
    game_name: str
    avatar_url: str
    achievements: tuple[AchievementRow, ...]


CardItem = GameStatusItem | AchievementItem


@dataclass(frozen=True)
class _Theme:
    """一份配色：状态条 / 昵称 / 群名 / 副标题 / 游戏名。"""

    bar: str
    persona: str
    group: str
    subtitle: str
    game: str


# 解锁成就说明玩家正在游戏中，成就卡沿用「开始游戏」的在线绿色
_ONLINE_THEME = _Theme("#5cbe32", "#e1e1e1", "#8f98a0", "#808a94", "#90ba3c")

_THEMES: dict[str, _Theme] = {
    "开始游戏": _ONLINE_THEME,
    "结束游戏": _Theme("#57cbde", "#57cbde", "#4c91ac", "#808a94", "#57cbde"),
    "用户上线": _Theme("#57cbde", "#57cbde", "#4c91ac", "#808a94", ""),
    "用户离线": _Theme("#6b7280", "#c7ccd1", "#8f98a0", "#8b929c", ""),
    ACHIEVEMENT_KIND: _ONLINE_THEME,
}

_SUBTITLES: dict[str, str] = {
    "开始游戏": "正在玩",
    "结束游戏": "已结束游玩",
    "用户上线": "已上线",
    "用户离线": "已离线",
}


def _format_time(ts: int) -> str:
    """解锁时间按本地时区显示；时间戳缺失时留空。"""
    if ts <= 0:
        return ""
    return time.strftime(_TIME_FORMAT, time.localtime(ts))


def _avatar_box(avatar_url: str, bar_color: str) -> str:
    return (
        '<div class="avatar-box">'
        f'<img class="avatar" src="{html.escape(avatar_url)}" alt="">'
        f'<div class="status-bar" style="background-color: {bar_color};"></div>'
        "</div>"
    )


def _persona_row(nickname: str, group_name: str, theme: _Theme) -> str:
    return (
        '<div class="persona-row">'
        f'<span class="persona-name" style="color: {theme.persona};">{html.escape(nickname)}</span>'
        f'<span class="group-name" style="color: {theme.group};">({html.escape(group_name)})</span>'
        "</div>"
    )


def _status_html(item: GameStatusItem) -> str:
    theme = _THEMES[item.kind]
    cover_html = ""
    if item.cover_url:
        cover_html = f'<img class="cover-img" src="{html.escape(item.cover_url)}" alt="">'
    game_html = ""
    if item.kind in GAME_KINDS:
        game_html = f'<div class="game-name" style="color: {theme.game};">{html.escape(item.game_name)}</div>'
    info = (
        '<div class="info-row">'
        f"{_avatar_box(item.avatar_url, theme.bar)}"
        '<div class="text-area">'
        f"{_persona_row(item.nickname, item.group_name, theme)}"
        f'<div class="subtitle" style="color: {theme.subtitle};">{_SUBTITLES[item.kind]}</div>'
        f"{game_html}"
        "</div>"
        "</div>"
    )
    return f'<div class="game-status-card">{cover_html}{info}</div>'


def _achievement_row_html(row: AchievementRow) -> str:
    icon_html = ""
    if row.icon_url:
        icon_html = f'<img class="achievement-icon" src="{html.escape(row.icon_url)}" alt="">'
    desc_html = ""
    if row.description:
        desc_html = f'<div class="achievement-desc">{html.escape(row.description)}</div>'
    return (
        '<div class="achievement-row">'
        f'<div class="achievement-icon-box">{icon_html}</div>'
        '<div class="achievement-text">'
        f'<div class="achievement-name">{html.escape(row.name)}</div>'
        f"{desc_html}"
        "</div>"
        f'<div class="achievement-time">{_format_time(row.unlocked_at)}</div>'
        "</div>"
    )


def _achievement_html(item: AchievementItem) -> str:
    theme = _THEMES[ACHIEVEMENT_KIND]
    shown = item.achievements[: _MAX_ACHIEVEMENT_ROWS]
    rows = "".join(_achievement_row_html(row) for row in shown)
    more_html = ""
    if len(item.achievements) > _MAX_ACHIEVEMENT_ROWS:
        more_html = f'<div class="achievement-more">等共 {len(item.achievements)} 个成就</div>'
    subtitle = (
        "在 "
        f'<span class="game-name-text" style="color: {theme.game};">{html.escape(item.game_name)}</span>'
        " 解锁了成就"
    )
    info = (
        '<div class="info-row">'
        f"{_avatar_box(item.avatar_url, theme.bar)}"
        '<div class="text-area">'
        f"{_persona_row(item.nickname, item.group_name, theme)}"
        f'<div class="subtitle" style="color: {theme.subtitle};">{subtitle}</div>'
        "</div>"
        "</div>"
    )
    return (
        '<div class="game-status-card achievement-card">'
        f"{info}"
        f'<div class="achievement-list">{rows}{more_html}</div>'
        "</div>"
    )


def _card_html(item: CardItem) -> str:
    if isinstance(item, AchievementItem):
        return _achievement_html(item)
    return _status_html(item)


def _card_height(item: CardItem) -> int:
    """估高只用于给浏览器留视口，实际截图按元素高度裁切。"""
    if isinstance(item, AchievementItem):
        rows = min(len(item.achievements), _MAX_ACHIEVEMENT_ROWS)
        more = _ACHIEVEMENT_MORE_HEIGHT if len(item.achievements) > _MAX_ACHIEVEMENT_ROWS else 0
        return _ROW_HEIGHT + _ACHIEVEMENT_LIST_PADDING + _ACHIEVEMENT_ROW_HEIGHT * rows + more
    return _ROW_HEIGHT + (_COVER_HEIGHT if item.cover_url else 0)


def _columns(count: int) -> int:
    return max(1, min(count, _MAX_COLUMNS))


def _content_height(items: Sequence[CardItem]) -> int:
    """按每行最高的卡片累加，得到整页内容高度。"""
    height = 0
    for start in range(0, len(items), _MAX_COLUMNS):
        chunk = items[start : start + _MAX_COLUMNS]
        height += max(_card_height(item) for item in chunk)
    return height


def render_game_status_html(items: Sequence[CardItem]) -> str:
    """拼装卡片页面；多张时横向换行排列，末行右侧留底色。"""
    cards = "\n".join(_card_html(item) for item in items)
    template = get_template("steam_game_status.html")
    return template.render(
        styles=read_styles("common.css", "game_status.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        card_bg_url=get_bg_url(),
        cards=cards,
        card_width=_CARD_WIDTH,
        columns=_columns(len(items)),
    )


async def render_game_status(items: Sequence[CardItem]) -> bytes:
    """把 1~N 张卡片渲染成 JPEG 字节，整页一次截图。"""
    if not items:
        raise ValueError("render_game_status 需要至少一张卡片")
    html_content = render_game_status_html(items)
    single = len(items) == 1
    # 合并图很宽，降一点像素比与质量，避免消息体过大
    return await render_html(
        html_content,
        "#game-status-list",
        viewport_width=_columns(len(items)) * _CARD_WIDTH + 50,
        viewport_height=_content_height(items) + 50,
        device_scale_factor=2.0 if single else 1.5,
        quality=85 if single else 80,
    )
