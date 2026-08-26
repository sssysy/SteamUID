import datetime
import html as html_lib
import pathlib

from ..render import (
    _DEFAULT_GAME_COVER_SVG,
    _fill_template,
    _get_default_icon_b64,
    render_html,
)
from .account_pill import render_account_pill_html

_WISHLIST_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "wishlist.html"


def format_date_added(date_added: int | float | str | None) -> str:
    """将 Unix 秒时间戳格式化为 YYYY-MM-DD。"""
    if not date_added:
        return "--"
    if isinstance(date_added, (int, float)):
        try:
            dt = datetime.datetime.fromtimestamp(date_added)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return "--"
    return str(date_added)


def render_wishlist_html(
    wishlist_data: list[dict],
    user_data: dict | None = None,
    canvas_width: int = 800,
    title_text: str | None = None,
) -> str:
    """构建 Steam 愿望单列表卡片的 HTML 字符串。

    wishlist_data 列表项字典格式:
        - appid: str | int
        - game_name: str
        - cover_url: str (可选)
        - date_added: int | str (Unix 时间戳或日期字符串)
        - price_str: str (格式化价格，如 "¥ 198"、"免费"、"未发售")
        - discount_percent: int (折扣百分比，如 50 表示 -50%)
        - is_free: bool (是否免费)
        - is_unreleased: bool (是否未发售/暂无定价)

    user_data 字典格式 (可选):
        - name: str (Steam 昵称)
        - friend_code: str (Steam 好友码)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)
    """
    template = _WISHLIST_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_avatar = _get_default_icon_b64()

    # 1. 顶部账号胶囊卡片
    account_pill_html = render_account_pill_html(user_data, default_avatar)

    # 2. 标题文字
    if title_text is None:
        title_text = "steam 愿望单列表"

    if not wishlist_data:
        items_html = '<div class="empty-state">该 Steam 账号愿望单暂无游戏数据</div>'
    else:
        items_html_parts = []
        for item in wishlist_data:
            appid = str(item.get("appid", ""))
            game_name = item.get("game_name", "") or appid
            cover_url = (
                item.get("cover_url")
                or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
            )
            raw_date = item.get("date_added")
            date_str = format_date_added(raw_date)

            is_free = item.get("is_free", False)
            is_unreleased = item.get("is_unreleased", False)
            discount_pct = int(item.get("discount_percent") or 0)
            price_str = str(item.get("price_str") or "")

            escaped_name = html_lib.escape(game_name)
            escaped_appid = html_lib.escape(appid)
            escaped_date = html_lib.escape(date_str)
            appid_html = f'<div class="game-appid">AppID: {escaped_appid}</div>' if appid else ""

            # 价格部分排版
            if is_free:
                price_inner = '<div class="price-free">免费</div>'
            elif is_unreleased:
                price_inner = f'<div class="price-unreleased">{html_lib.escape(price_str or "未发售")}</div>'
            elif discount_pct > 0:
                price_inner = (
                    f'<span class="discount-badge">-{discount_pct}%</span>'
                    f'<span class="price-text">{html_lib.escape(price_str)}</span>'
                )
            elif price_str:
                price_inner = f'<div class="price-text">{html_lib.escape(price_str)}</div>'
            else:
                price_inner = '<div class="price-unreleased">暂无定价</div>'

            item_html = (
                f'<div class="wishlist-item">'
                f'  <div class="game-info-col">'
                f'    <div class="game-cover-wrapper">'
                f'      <img class="game-cover" src="{cover_url}" onerror="this.onerror=null;this.src=\'{_DEFAULT_GAME_COVER_SVG}\'" alt="">'
                f'    </div>'
                f'    <div class="game-meta">'
                f'      <div class="game-name" title="{escaped_name}">{escaped_name}</div>'
                f'      {appid_html}'
                f'    </div>'
                f'  </div>'
                f'  <div class="data-cols">'
                f'    <div class="date-text">{escaped_date}</div>'
                f'    <div class="price-col">{price_inner}</div>'
                f'  </div>'
                f'</div>'
            )
            items_html_parts.append(item_html)

        items_html = "\n".join(items_html_parts)

    replacements = {
        "canvas_width": str(canvas_width),
        "title_text": title_text,
        "account_pill_html": account_pill_html,
        "items_html": items_html,
    }

    return _fill_template(template, replacements)


async def render_wishlist(
    wishlist_data: list[dict],
    user_data: dict | None = None,
    title_text: str | None = None,
    canvas_width: int = 800,
) -> bytes:
    """渲染 Steam 愿望单卡片为 PNG 字节。"""
    html_content = render_wishlist_html(
        wishlist_data=wishlist_data,
        user_data=user_data,
        canvas_width=canvas_width,
        title_text=title_text,
    )
    item_count = len(wishlist_data)
    est_height = max(240, 110 + item_count * 58 + 60 + 35)

    return await render_html(
        html_content,
        ".wishlist-container",
        viewport_width=canvas_width + 40,
        viewport_height=est_height,
        device_scale_factor=2.0,
    )
