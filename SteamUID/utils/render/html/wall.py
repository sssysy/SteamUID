"""游戏墙卡片：顶部标题与用户胶囊，下方按时长分跨度的封面网格。"""

import html
import math
from dataclasses import dataclass
from collections.abc import Sequence

from .render import read_styles, render_html, get_template
from .card_footer import footer_html
from .account_pill import PillAccount, pill_html
from .static_assets import get_font_url
from ...helper.library import span_of

_FONT_REGULAR = "steam-Regular.ttf"
_FONT_MEDIUM = "steam-Medium.ttf"
_FONT_BOLD = "steam-Bold.ttf"

_CANVAS_WIDTH = 1200
_COLUMNS = 8
# 网格下方说明行的高度，仅在有说明内容时计入视口
_NOTE_HEIGHT = 34
DEFAULT_WALL_TITLE = "steam游戏墙"
# 行高与模板里 grid-auto-rows 的换算一致，仅用于估算初始视口高度
_ROW_HEIGHT = _CANVAS_WIDTH / _COLUMNS * 215 / 460
# 顶部栏 = 上下内边距 44px + 药丸 74px
_HEADER_HEIGHT = 118
_FOOTER_HEIGHT = 48
# 格子多到出超长图时降清晰度，压住截图内存与消息体
_LARGE_WALL_ROWS = 24


@dataclass(frozen=True)
class WallGame:
    """墙上一款游戏：时长决定格子跨度，封面缺失时只留透明占位格。"""

    name: str
    playtime_minutes: int
    cover_url: str


def _game_html(game: WallGame) -> str:
    span = span_of(game.playtime_minutes)
    style = f"grid-column: span {span}; grid-row: span {span};"
    if not game.cover_url:
        return f'<div class="game" style="{style}"></div>'
    return f'<div class="game" style="{style}"><img class="game-img" src="{html.escape(game.cover_url)}" alt=""></div>'


def _note_html(note: str) -> str:
    """网格下方的补充说明行；无内容时不渲染节点。"""
    if not note.strip():
        return ""
    return f'<div class="wall-note">{html.escape(note)}</div>'


def render_game_wall_html(
    user: PillAccount,
    games: Sequence[WallGame],
    *,
    title: str = DEFAULT_WALL_TITLE,
    note: str = "",
) -> str:
    """拼装游戏墙卡片 HTML；title 与 note 供复用同一张墙的其它命令覆盖。"""
    grid = "\n".join(_game_html(game) for game in games)
    template = get_template("steam_wall.html")
    return template.render(
        styles=read_styles("common.css", "wall.css"),
        font_regular_url=get_font_url(_FONT_REGULAR),
        font_medium_url=get_font_url(_FONT_MEDIUM),
        font_bold_url=get_font_url(_FONT_BOLD),
        canvas_width=_CANVAS_WIDTH,
        title=title,
        account_pill_html=pill_html(user),
        grid_html=f'<div class="game-wall-grid">\n{grid}\n</div>',
        note_html=_note_html(note),
        footer_html=footer_html(),
    )


async def render_game_wall(
    user: PillAccount,
    games: Sequence[WallGame],
    *,
    title: str = DEFAULT_WALL_TITLE,
    note: str = "",
) -> bytes:
    """渲染游戏墙为 JPEG 字节；note 为空时不计入视口高度。"""
    if not games:
        raise ValueError("没有可上墙的游戏")

    html_content = render_game_wall_html(user, games, title=title, note=note)
    cells = sum(span_of(game.playtime_minutes) ** 2 for game in games)
    rows = max(1, math.ceil(cells / _COLUMNS))
    large = rows > _LARGE_WALL_ROWS
    note_height = _NOTE_HEIGHT if note.strip() else 0

    return await render_html(
        html_content,
        "#steam-wall-card",
        viewport_width=_CANVAS_WIDTH + 40,
        viewport_height=int(_HEADER_HEIGHT + rows * _ROW_HEIGHT + note_height + _FOOTER_HEIGHT) + 20,
        device_scale_factor=1.5 if large else 2.0,
        quality=80 if large else 85,
    )
