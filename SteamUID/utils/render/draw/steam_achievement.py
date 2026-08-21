import html as html_lib
import pathlib

from ..render import (
    _fill_template,
    _get_default_icon_b64,
    _get_footer_b64,
    render_html,
)
from .account_pill import render_account_pill_html

_STEAM_ACHIEVEMENT_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "steam_achievement.html"


def render_steam_achievement_html(
    game_data: dict,
    user_data: dict,
    achievements_data: list[dict],
    canvas_width: int | None = None,
) -> str:
    """构建 Steam 游戏成就卡片的 HTML 字符串。

    game_data 格式:
        - name: str (游戏名称)
        - icon_url: str (游戏方形图标 URL)
        - cover_url: str (游戏横版封面 URL，用于顶部高斯模糊背景)

    user_data 格式:
        - name: str (Steam 昵称)
        - friend_code: str (Steam 好友码)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)

    achievements_data 格式:
        - name: str (成就名称)
        - description: str (成就描述)
        - icon: str (成就图标 URL)
        - achieved: bool (是否已解锁)
        - unlock_time_str: str | None (如 "解锁时间: 2026年6月15日 10:33")
    """
    template = _STEAM_ACHIEVEMENT_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_icon = _get_default_icon_b64()
    default_avatar = default_icon

    # 1. 游戏信息
    game_name = html_lib.escape(game_data.get("name", "未知游戏"))
    game_icon_url = game_data.get("icon_url") or default_icon
    cover_url = game_data.get("cover_url") or game_icon_url

    # 2. 用户账号卡片
    account_pill_html = render_account_pill_html(user_data, default_avatar)

    # 3. 统计与进度
    total_count = len(achievements_data)
    unlocked_count = sum(1 for a in achievements_data if a.get("achieved"))
    percentage = round(unlocked_count / total_count * 100) if total_count > 0 else 0

    # 4. 超限处理与分列
    # 最多 3 列，每列 20 个（共 60 个槽位）
    if total_count > 60:
        display_items = list(achievements_data[:59])
        remaining_count = total_count - 59
        display_items.append({
            "name": f"剩余 {remaining_count} 项成就未显示",
            "description": "成就过多，更多成就请通过steam查看。",
            "icon": "",
            "achieved": False,
            "unlock_time_str": "",
            "is_overflow": True,
        })
    else:
        display_items = list(achievements_data)

    num_display = len(display_items)
    if canvas_width is None:
        if num_display <= 20:
            canvas_width = 720
        elif num_display <= 40:
            canvas_width = 1380
        else:
            canvas_width = 2040

    if not display_items:
        columns_html = '<div class="empty-state">该游戏暂无成就数据</div>'
    else:
        if num_display <= 20:
            num_cols = 1
        elif num_display <= 40:
            num_cols = 2
        else:
            num_cols = 3

        base_size = num_display // num_cols
        remainder = num_display % num_cols

        columns_html_parts = []
        start_idx = 0
        for col_idx in range(num_cols):
            col_size = base_size + (1 if col_idx < remainder else 0)
            chunk = display_items[start_idx : start_idx + col_size]
            start_idx += col_size

            card_parts = []
            for item in chunk:
                name = html_lib.escape(item.get("name", ""))
                desc = html_lib.escape(item.get("description", ""))
                achieved = item.get("achieved", False)
                is_overflow = item.get("is_overflow", False)
                icon_url = item.get("icon", "")
                unlock_time = item.get("unlock_time_str", "")

                if is_overflow:
                    card_html = (
                        f'<div class="ach-card">\n'
                        f'  <div class="ach-icon-box overflow-icon">?</div>\n'
                        f'  <div class="ach-info">\n'
                        f'    <div class="ach-name" title="{name}">{name}</div>\n'
                        f'    <div class="ach-desc" title="{desc}">{desc}</div>\n'
                        f'  </div>\n'
                        f'</div>'
                    )
                elif achieved:
                    time_html = (
                        f'<div class="ach-time">{html_lib.escape(unlock_time)}</div>'
                        if unlock_time
                        else ""
                    )
                    card_html = (
                        f'<div class="ach-card">\n'
                        f'  <div class="ach-icon-box">\n'
                        f'    <img class="ach-icon" src="{icon_url}" onerror="this.src=\'{default_icon}\'" alt="">\n'
                        f'  </div>\n'
                        f'  <div class="ach-info">\n'
                        f'    <div class="ach-name" title="{name}">{name}</div>\n'
                        f'    <div class="ach-desc" title="{desc}">{desc}</div>\n'
                        f'  </div>\n'
                        f'  {time_html}\n'
                        f'</div>'
                    )
                else:
                    card_html = (
                        f'<div class="ach-card locked">\n'
                        f'  <div class="ach-icon-box">\n'
                        f'    <img class="ach-icon" src="{icon_url}" onerror="this.src=\'{default_icon}\'" alt="">\n'
                        f'  </div>\n'
                        f'  <div class="ach-info">\n'
                        f'    <div class="ach-name" title="{name}">{name}</div>\n'
                        f'    <div class="ach-desc" title="{desc}">{desc}</div>\n'
                        f'  </div>\n'
                        f'</div>'
                    )
                card_parts.append(card_html)

            col_inner = "\n".join(card_parts)
            columns_html_parts.append(f'<div class="ach-column">\n{col_inner}\n</div>')

        columns_inner = "\n".join(columns_html_parts)
        columns_html = f'<div class="columns-container">\n{columns_inner}\n</div>'

    replacements = {
        "canvas_width": str(canvas_width),
        "cover_url": cover_url,
        "game_icon_url": game_icon_url,
        "game_name": game_name,
        "default_icon": default_icon,
        "account_pill_html": account_pill_html,
        "unlocked_count": str(unlocked_count),
        "total_count": str(total_count),
        "percentage": str(percentage),
        "columns_html": columns_html,
        "footer_b64": _get_footer_b64(),
    }

    return _fill_template(template, replacements)


async def render_steam_achievement(
    game_data: dict,
    user_data: dict,
    achievements_data: list[dict],
) -> bytes:
    """渲染 Steam 游戏成就卡片为 PNG 字节。"""
    num_items = len(achievements_data)
    num_display = min(num_items, 60)
    if num_display <= 20:
        canvas_width = 720
        max_rows = max(1, num_display)
    elif num_display <= 40:
        canvas_width = 1380
        max_rows = (num_display + 1) // 2
    else:
        canvas_width = 2040
        max_rows = (num_display + 2) // 3

    html_content = render_steam_achievement_html(
        game_data=game_data,
        user_data=user_data,
        achievements_data=achievements_data,
        canvas_width=canvas_width,
    )
    est_height = max(500, 200 + max_rows * 78 + 40) + 35

    return await render_html(
        html_content,
        ".steam-achievement-card",
        viewport_width=canvas_width + 40,
        viewport_height=est_height,
        device_scale_factor=2.0,
    )
