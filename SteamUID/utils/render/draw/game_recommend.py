import html as html_lib
import pathlib

from ..render import (
    _DEFAULT_GAME_COVER_SVG,
    _fill_template,
    _get_default_icon_b64,
    render_html,
)
from .account_pill import render_account_pill_html

_GAME_RECOMMEND_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "game_recommend.html"


def render_game_recommend_html(
    games_data: list[dict],
    user_data: dict | None = None,
    canvas_width: int = 880,
) -> str:
    """构建 Steam 库存游戏推荐（玩什么）卡片的 HTML 字符串。

    games_data item 字典格式:
        - appid: str | int
        - name: str
        - description: str (游戏简介)
        - cover_url: str (横板封面 URL，可选)

    user_data 字典格式 (可选):
        - name: str (Steam 昵称)
        - friend_code: str (Steam 好友码)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)
    """
    template = _GAME_RECOMMEND_TEMPLATE_PATH.read_text(encoding="utf-8")
    title_text = "steam 库存游戏推荐"
    default_avatar = _get_default_icon_b64()

    # 右上角用户账号卡片
    account_pill_html = render_account_pill_html(user_data, default_avatar)

    cards_html_parts = []
    for item in games_data:
        appid = str(item.get("appid", ""))
        name = item.get("name", "") or "未知游戏"
        description = item.get("description", "") or "暂无游戏简介"
        cover_url = (
            item.get("cover_url")
            or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
        )

        escaped_name = html_lib.escape(name)
        escaped_desc = html_lib.escape(description)

        card_html = (
            f'<div class="game-card">'
            f'  <div class="cover-wrapper">'
            f'    <img class="cover-img" src="{cover_url}" onerror="this.onerror=null;this.src=\'{_DEFAULT_GAME_COVER_SVG}\'" alt="">'
            f'  </div>'
            f'  <div class="card-info">'
            f'    <div class="game-name" title="{escaped_name}">{escaped_name}</div>'
            f'    <div class="game-desc">{escaped_desc}</div>'
            f'  </div>'
            f'</div>'
        )
        cards_html_parts.append(card_html)

    cards_html = "\n".join(cards_html_parts)

    replacements = {
        "canvas_width": str(canvas_width),
        "title_text": title_text,
        "account_pill_html": account_pill_html,
        "cards_html": cards_html,
    }

    return _fill_template(template, replacements)


async def render_game_recommend(
    games_data: list[dict],
    user_data: dict | None = None,
) -> bytes:
    """渲染 Steam 库存游戏推荐卡片为 PNG 字节。"""
    canvas_w = 880
    html_content = render_game_recommend_html(
        games_data=games_data,
        user_data=user_data,
        canvas_width=canvas_w,
    )
    return await render_html(
        html_content,
        ".recommend-container",
        viewport_width=canvas_w + 50,
        viewport_height=600,
        device_scale_factor=2.0,
    )
