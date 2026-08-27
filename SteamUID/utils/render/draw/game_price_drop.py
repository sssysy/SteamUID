import html as html_lib
import pathlib

from ..render import (
    _DEFAULT_GAME_COVER_SVG,
    _fill_template,
    render_html,
)

_PRICE_DROP_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "game_price_drop.html"


def render_game_price_drop_html(
    *,
    game_name: str,
    game_desc: str = "",
    cover_url: str | None = None,
    discount_percent: int | str = 0,
    original_price: str = "",
    final_price: str = "",
    canvas_width: int = 380,
) -> str:
    """构建 Steam 游戏降价卡片的 HTML 字符串。

    参数:
        game_name: 游戏名称
        game_desc: 游戏简介（short_description）
        cover_url: 游戏横板封面图 URL（header_image）
        discount_percent: 折扣百分比数字（如 50 代表 -50%）
        original_price: 原价格式化字符串（如 ¥ 198）
        final_price: 现价/折后价格式化字符串（如 ¥ 99）
        canvas_width: 卡片宽度（默认 380px）
    """
    template = _PRICE_DROP_TEMPLATE_PATH.read_text(encoding="utf-8")

    escaped_name = html_lib.escape(game_name or "未知游戏")
    escaped_desc = html_lib.escape(game_desc or "暂无游戏简介")

    # 左侧横板封面背景
    if cover_url:
        cover_html = f'<div class="cover-bg" style="background-image: url(\'{cover_url}\');"></div>'
    else:
        cover_html = f'<div class="cover-bg" style="background-image: url(\'{_DEFAULT_GAME_COVER_SVG}\');"></div>'

    # 折扣与价格标签组件（参考 Steam 官方折扣标签条渲染）
    try:
        discount_val = int(discount_percent)
    except (ValueError, TypeError):
        discount_val = 0

    escaped_orig = html_lib.escape(str(original_price))
    escaped_final = html_lib.escape(str(final_price))

    if discount_val > 0:
        pct_text = f"-{discount_val}%"
        orig_html = f'<span class="discount-original-price">{escaped_orig}</span>' if escaped_orig else ""
        price_html = (
            f'<div class="discount-block">'
            f'  <div class="discount-pct">{pct_text}</div>'
            f'  <div class="discount-prices">'
            f'    {orig_html}'
            f'    <span class="discount-final-price">{escaped_final}</span>'
            f'  </div>'
            f'</div>'
        )
    else:
        price_html = (
            f'<div class="discount-block">'
            f'  <div class="discount-prices">'
            f'    <span class="discount-final-price">{escaped_final}</span>'
            f'  </div>'
            f'</div>'
        )

    replacements = {
        "canvas_width": str(canvas_width),
        "cover_html": cover_html,
        "game_name": escaped_name,
        "game_desc": escaped_desc,
        "price_html": price_html,
    }

    return _fill_template(template, replacements)


async def render_game_price_drop(
    *,
    game_name: str,
    game_desc: str = "",
    cover_url: str | None = None,
    discount_percent: int | str = 0,
    original_price: str = "",
    final_price: str = "",
    canvas_width: int = 380,
) -> bytes:
    """渲染 Steam 游戏降价卡片为 JPEG 图片字节。"""
    html_content = render_game_price_drop_html(
        game_name=game_name,
        game_desc=game_desc,
        cover_url=cover_url,
        discount_percent=discount_percent,
        original_price=original_price,
        final_price=final_price,
        canvas_width=canvas_width,
    )
    return await render_html(
        html_content,
        ".price-drop-card",
        viewport_width=canvas_width + 40,
        viewport_height=400,
        device_scale_factor=2.0,
    )
