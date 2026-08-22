import html as html_lib
import pathlib

from ..render import (
    _DEFAULT_GAME_COVER_SVG,
    _fill_template,
    format_ranking_duration,
    render_html,
)

_GAME_RANKING_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "game_ranking.html"


def render_game_ranking_html(
    ranking_data: list[dict],
    top_count: int | None = None,
    canvas_width: int = 680,
) -> str:
    """构建 Steam 群游戏排行榜卡片的 HTML 字符串。

    ranking_data item 字典格式:
        - appid: str
        - game_name: str
        - total_duration: int (秒)
        - cover_url: str (可选)
    """
    template = _GAME_RANKING_TEMPLATE_PATH.read_text(encoding="utf-8")
    actual_count = len(ranking_data)
    title_text = f"steam 群游戏排行 Top{actual_count}: "

    items_html_parts = []
    for idx, item in enumerate(ranking_data, 1):
        appid = str(item.get("appid", ""))
        game_name = item.get("game_name", "") or appid
        cover_url = (
            item.get("cover_url")
            or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
        )
        duration_sec = item.get("total_duration", 0)
        duration_str = format_ranking_duration(duration_sec)
        rank_str = f"#{idx}"

        escaped_name = html_lib.escape(game_name)

        item_html = (
            f'<div class="ranking-item">'
            f'  <div class="game-info-col">'
            f'    <div class="game-cover-wrapper">'
            f'      <img class="game-cover" src="{cover_url}" onerror="this.onerror=null;this.src=\'{_DEFAULT_GAME_COVER_SVG}\'" alt="">'
            f'    </div>'
            f'    <div class="game-name" title="{escaped_name}">{escaped_name}</div>'
            f'  </div>'
            f'  <div class="data-cols">'
            f'    <div class="rank-num">{rank_str}</div>'
            f'    <div class="duration-text">{duration_str}</div>'
            f'  </div>'
            f'</div>'
        )
        items_html_parts.append(item_html)

    items_html = "\n".join(items_html_parts)

    replacements = {
        "canvas_width": str(canvas_width),
        "title_text": title_text,
        "items_html": items_html,
    }

    return _fill_template(template, replacements)


async def render_game_ranking(
    ranking_data: list[dict],
    top_count: int | None = None,
) -> bytes:
    """渲染 Steam 群游戏排行榜卡片为 PNG 字节。"""
    canvas_w = 680
    html_content = render_game_ranking_html(ranking_data, top_count, canvas_width=canvas_w)
    item_count = len(ranking_data)
    est_height = 80 + item_count * 58 + 50 + 35
    return await render_html(
        html_content,
        ".ranking-container",
        viewport_width=canvas_w + 50,
        viewport_height=max(est_height, 200),
        device_scale_factor=2.0,
    )
