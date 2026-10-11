"""成就卡：复刻 Steam 成就页排版，封面模糊头图 + 进度条 + 多列成就列表。"""

import html
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections.abc import Sequence

from .render import get_template, read_styles, render_html
from .account_pill import PillAccount, pill_html
from .card_footer import footer_html
from .static_assets import get_font_url, get_texture_url

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"
_DEFAULT_ICON_NAME = "default_icon.jpg"

# 画布三档宽度与分列阈值，与旧版成就卡版式一致
_CANVAS_NARROW = 720
_CANVAS_MEDIUM = 1380
_CANVAS_WIDE = 2040
_SINGLE_COLUMN_MAX = 20
_DOUBLE_COLUMN_MAX = 40
# 最多铺 60 张成就卡，第 60 张留给「剩余 N 项」汇总
_MAX_SLOTS = 60
# 视口高度估算：每行成就 78px，另加头部与页脚余量；截取仍以元素实际高度为准
_ROW_HEIGHT = 78
_HEIGHT_EXTRA = 35
# 解锁时间固定按 UTC+8 展示，与 Steam 中文页一致
_UNLOCK_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class AchievementSlot:
    """一条成就：图标直链与解锁时间戳，文案与日期格式化留给渲染层。"""

    name: str
    description: str
    icon_url: str
    achieved: bool
    unlocked_at: int = 0
    overflow: bool = False


@dataclass(frozen=True)
class AchievementCard:
    """一张成就卡的渲染数据；封面与图标均为挂载直链。"""

    game_name: str
    game_icon_url: str
    cover_url: str
    account: PillAccount
    achievements: tuple[AchievementSlot, ...]


def _unlock_text(ts: int) -> str:
    """解锁时间文案；时间戳缺失时留空。"""
    if ts <= 0:
        return ""
    moment = datetime.fromtimestamp(ts, tz=_UNLOCK_TZ)
    return (
        f"解锁时间: {moment.year}年{moment.month}月{moment.day}日 "
        f"{moment.hour:02d}:{moment.minute:02d}"
    )


def _column_count(total: int) -> int:
    """按条数定列数：≤20 一列、≤40 两列、其余三列。"""
    if total <= _SINGLE_COLUMN_MAX:
        return 1
    if total <= _DOUBLE_COLUMN_MAX:
        return 2
    return 3


def _canvas_width(total: int) -> int:
    """画布宽度与列数同步分档，避免单列铺太宽。"""
    if total <= _SINGLE_COLUMN_MAX:
        return _CANVAS_NARROW
    if total <= _DOUBLE_COLUMN_MAX:
        return _CANVAS_MEDIUM
    return _CANVAS_WIDE


def displayed_slots(achievements: Sequence[AchievementSlot]) -> list[AchievementSlot]:
    """卡片实际铺出的成就；超出上限时末位折叠成一条汇总。"""
    if len(achievements) <= _MAX_SLOTS:
        return list(achievements)

    shown = list(achievements[: _MAX_SLOTS - 1])
    remaining = len(achievements) - (_MAX_SLOTS - 1)
    shown.append(
        AchievementSlot(
            name=f"剩余 {remaining} 项成就未显示",
            description="成就过多，更多成就请通过steam查看。",
            icon_url="",
            achieved=False,
            overflow=True,
        )
    )
    return shown


def _icon_image_html(icon_url: str, default_icon: str) -> str:
    """成就图标；外链失效时回落到默认图标，兜底地址由挂载直链给出。"""
    return (
        f'<img class="ach-icon" src="{html.escape(icon_url)}" '
        f"onerror=\"this.onerror=null;this.src='{default_icon}'\" alt=\"\">"
    )


def _slot_html(slot: AchievementSlot, default_icon: str) -> str:
    name = html.escape(slot.name)
    description = html.escape(slot.description)
    info = (
        '<div class="ach-info">'
        f'<div class="ach-name" title="{name}">{name}</div>'
        f'<div class="ach-desc" title="{description}">{description}</div>'
        "</div>"
    )
    if slot.overflow:
        return (
            '<div class="ach-card">'
            '<div class="ach-icon-box overflow-icon">?</div>'
            f"{info}"
            "</div>"
        )

    icon = f'<div class="ach-icon-box">{_icon_image_html(slot.icon_url, default_icon)}</div>'
    if not slot.achieved:
        return f'<div class="ach-card locked">{icon}{info}</div>'

    unlock = _unlock_text(slot.unlocked_at)
    time_html = f'<div class="ach-time">{html.escape(unlock)}</div>' if unlock else ""
    return f'<div class="ach-card">{icon}{info}{time_html}</div>'


def _columns_html(slots: Sequence[AchievementSlot], default_icon: str) -> str:
    """分列：余数为前几列各多分一张，保证各列高度接近。"""
    columns = _column_count(len(slots))
    size, remainder = divmod(len(slots), columns)
    parts: list[str] = []
    start = 0
    for index in range(columns):
        width = size + (1 if index < remainder else 0)
        chunk = slots[start : start + width]
        start += width
        cards = "".join(_slot_html(slot, default_icon) for slot in chunk)
        parts.append(f'<div class="ach-column">{cards}</div>')
    return f'<div class="columns-container">{"".join(parts)}</div>'


def render_achievement_card_html(card: AchievementCard) -> str:
    """拼装成就卡 HTML；画布宽度与列数由展示条数决定。"""
    slots = displayed_slots(card.achievements)
    total = len(card.achievements)
    unlocked = sum(1 for slot in card.achievements if slot.achieved)
    percentage = round(unlocked / total * 100) if total > 0 else 0

    default_icon = get_texture_url(_DEFAULT_ICON_NAME)
    game_icon = card.game_icon_url or default_icon
    template = get_template("steam_achievement.html")
    return template.render(
        styles=read_styles("common.css", "achievement.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        canvas_width=_canvas_width(len(slots)),
        cover_url=html.escape(card.cover_url or game_icon),
        game_icon_url=html.escape(game_icon),
        game_name=html.escape(card.game_name),
        default_icon=default_icon,
        account_pill_html=pill_html(card.account),
        unlocked_count=unlocked,
        total_count=total,
        percentage=percentage,
        columns_html=(
            _columns_html(slots, default_icon)
            if slots
            else '<div class="empty-state">该游戏暂无成就数据</div>'
        ),
        footer_html=footer_html(),
    )


async def render_achievement_card(card: AchievementCard) -> bytes:
    """渲染成就卡为 JPEG 字节；视口不足时渲染层会自动撑大再截取。"""
    total = len(displayed_slots(card.achievements))
    rows = max(1, -(-total // _column_count(total)))
    return await render_html(
        render_achievement_card_html(card),
        "#steam-achievement-card",
        viewport_width=_canvas_width(total) + 40,
        viewport_height=max(500, 200 + rows * _ROW_HEIGHT + 40) + _HEIGHT_EXTRA,
        device_scale_factor=2.0,
    )
