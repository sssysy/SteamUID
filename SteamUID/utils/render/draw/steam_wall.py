import pathlib

from ..render import (
    _fill_template,
    _get_default_icon_b64,
    render_html,
)
from .account_pill import render_account_pill_html

_STEAM_WALL_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "steam_wall.html"


def render_steam_wall_html(
    user_data: dict,
    games_data: list[dict],
    canvas_width: int = 1200,
) -> str:
    """构建 Steam 游戏墙卡片的 HTML 字符串。

    user_data 字典格式:
        - name: str (Steam 昵称)
        - friend_code: str (Steam 好友码)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)

    games_data 列表项格式:
        - appid: int | str
        - name: str (可选)
        - playtime_forever: int (总游玩时长，分钟)
        - cover_url: str (可选)
    """
    template = _STEAM_WALL_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_avatar = _get_default_icon_b64()

    # 1. 顶部用户账号卡片
    account_pill_html = render_account_pill_html(user_data, default_avatar)

    # 2. 游戏墙网格
    # 过滤游玩时长 < 10 分钟的游戏
    valid_games = [
        g for g in games_data
        if (g.get("playtime_forever") or 0) >= 10
    ]
    # 按游玩时长降序排序
    valid_games.sort(key=lambda g: g.get("playtime_forever", 0), reverse=True)

    if not valid_games:
        grid_html = '<div class="empty-state">该 Steam 账号暂无可展示的游戏库存（需游玩时长 ≥ 10 分钟）</div>'
    else:
        game_items_parts = []
        for g in valid_games:
            appid = str(g.get("appid", ""))
            playtime_min = g.get("playtime_forever", 0)
            playtime_hours = playtime_min / 60.0

            if playtime_hours > 1000:
                span = 4
            elif playtime_hours > 500:
                span = 3
            elif playtime_hours > 100:
                span = 2
            else:
                span = 1

            col_span, row_span = span, span

            cover_url = (
                g.get("cover_url")
                or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
            )

            item_html = (
                f'<div class="game" style="grid-column: span {col_span}; grid-row: span {row_span};">'
                f'  <img class="game-img" src="{cover_url}" onerror="this.closest(\'.game\')?.remove()" alt="">'
                f'</div>'
            )
            game_items_parts.append(item_html)

        grid_items_inner = "\n".join(game_items_parts)
        grid_html = f'<div class="game-wall-grid">\n{grid_items_inner}\n</div>'

    replacements = {
        "canvas_width": str(canvas_width),
        "account_pill_html": account_pill_html,
        "grid_html": grid_html,
    }

    return _fill_template(template, replacements)


async def render_steam_wall(
    user_data: dict,
    games_data: list[dict],
    canvas_width: int = 1200,
) -> bytes:
    """渲染 Steam 游戏墙卡片为 PNG 字节。"""
    html_content = render_steam_wall_html(
        user_data=user_data,
        games_data=games_data,
        canvas_width=canvas_width,
    )
    valid_count = len([g for g in games_data if (g.get("playtime_forever") or 0) >= 10])
    est_height = max(600, 140 + int(valid_count * 30)) + 40

    return await render_html(
        html_content,
        ".steam-wall-card",
        viewport_width=canvas_width + 40,
        viewport_height=est_height,
        device_scale_factor=2.0,
    )
