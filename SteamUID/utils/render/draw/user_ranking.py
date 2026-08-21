import html as html_lib
import pathlib

from ..render import (
    _fill_template,
    _get_default_icon_b64,
    _get_footer_b64,
    format_ranking_duration,
    render_html,
)

_USER_RANKING_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "html" / "user_ranking.html"


def render_user_ranking_html(
    ranking_data: list[dict],
    top_count: int | None = None,
    canvas_width: int = 680,
) -> str:
    """构建 Steam 群用户游玩时长排行榜卡片的 HTML 字符串。

    ranking_data item 字典格式:
        - user_id: str
        - user_name: str
        - total_duration: int (秒)
        - avatar_url: str (可选)
    """
    template = _USER_RANKING_TEMPLATE_PATH.read_text(encoding="utf-8")
    actual_count = len(ranking_data)
    title_text = f"steam群游玩时长排行 Top{actual_count}: "
    default_avatar = _get_default_icon_b64()

    items_html_parts = []
    for idx, item in enumerate(ranking_data, 1):
        uid = str(item.get("user_id", ""))
        user_name = item.get("user_name", "") or uid
        avatar_url = (
            item.get("avatar_url")
            or (f"https://q1.qlogo.cn/g?b=qq&nk={uid}&s=640" if uid.isdigit() else default_avatar)
        )
        duration_sec = item.get("total_duration", 0)
        duration_str = format_ranking_duration(duration_sec)
        rank_str = f"#{idx}"

        escaped_name = html_lib.escape(user_name)

        item_html = (
            f'<div class="ranking-item">'
            f'  <div class="user-info-col">'
            f'    <div class="user-avatar-wrapper">'
            f'      <img class="user-avatar" src="{avatar_url}" onerror="this.onerror=null;this.src=\'{default_avatar}\'" alt="">'
            f'    </div>'
            f'    <div class="user-name" title="{escaped_name}">{escaped_name}</div>'
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
        "footer_b64": _get_footer_b64(),
    }

    return _fill_template(template, replacements)


async def render_user_ranking(
    ranking_data: list[dict],
    top_count: int | None = None,
) -> bytes:
    """渲染 Steam 群用户游玩时长排行榜卡片为 PNG 字节。"""
    canvas_w = 680
    html_content = render_user_ranking_html(ranking_data, top_count, canvas_width=canvas_w)
    item_count = len(ranking_data)
    est_height = 80 + item_count * 58 + 50 + 35
    return await render_html(
        html_content,
        ".ranking-container",
        viewport_width=canvas_w + 50,
        viewport_height=max(est_height, 200),
        device_scale_factor=2.0,
    )
