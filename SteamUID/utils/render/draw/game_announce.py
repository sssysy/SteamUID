import datetime
import html as html_lib
import pathlib

from ...bbcode import steam_bbcode_to_html
from ..render import (
    _DEFAULT_GAME_COVER_SVG,
    _fill_template,
    render_html,
)

_GAME_ANNOUNCE_TEMPLATE_PATH = (
    pathlib.Path(__file__).parent.parent / "html" / "game_announce.html"
)

# Steam 事件类型中文映射
EVENT_TYPE_NAMES: dict[int, str] = {
    1: "社区活动",
    2: "游戏活动",
    3: "派对活动",
    4: "会议活动",
    5: "特别活动",
    6: "音乐与艺术",
    7: "体育活动",
    8: "出行活动",
    9: "聊天活动",
    10: "游戏发售",
    11: "直播活动",
    12: "补丁更新",
    13: "重大更新预告",
    14: "重大更新",
    15: "DLC 发售",
    16: "即将推出",
    17: "电竞赛事",
    18: "开发者直播",
    19: "特邀直播",
    20: "促销特惠",
    21: "道具特惠",
    22: "双倍经验",
    23: "掉落活动",
    24: "特权活动",
    25: "游戏挑战",
    26: "游戏比赛",
    27: "线下活动",
    28: "新闻公告",
    29: "测试版发布",
    30: "游戏内容更新",
    31: "免费试玩",
    32: "赛季发布",
    33: "赛季更新",
    34: "交叉推广",
    35: "游戏内活动",
}


def render_game_announce_html(
    announce_item: dict,
    appid: str,
    game_name: str,
    game_logo_url: str,
    canvas_width: int = 720,
) -> str:
    """构建指定游戏公告卡片的 HTML 字符串。

    announce_item 字段:
        - gid: str
        - title: str
        - post_time: int
        - event_type: int
        - headline: str
        - body: str (BBCode)
        - url: str
    """
    template = _GAME_ANNOUNCE_TEMPLATE_PATH.read_text(encoding="utf-8")

    title = announce_item.get("title") or "游戏公告"
    event_type = announce_item.get("event_type", 28)
    event_type_str = EVENT_TYPE_NAMES.get(event_type, "官方公告")
    post_time = announce_item.get("post_time", 0)

    if post_time > 0:
        dt = datetime.datetime.fromtimestamp(post_time)
        date_str = dt.strftime("%Y-%m-%d %H:%M")
        event_tag = f"{event_type_str} · {date_str}"
    else:
        event_tag = event_type_str

    raw_body = announce_item.get("body", "")
    content_html = steam_bbcode_to_html(raw_body)
    if not content_html.strip():
        headline = announce_item.get("headline", "")
        content_html = f"<p>{html_lib.escape(headline)}</p>" if headline else "<p>暂无正文内容</p>"

    escaped_title = html_lib.escape(title)
    escaped_game_name = html_lib.escape(game_name)

    replacements = {
        "canvas_width": str(canvas_width),
        "event_tag": event_tag,
        "announce_title": escaped_title,
        "game_name": escaped_game_name,
        "game_logo_url": game_logo_url,
        "default_cover": _DEFAULT_GAME_COVER_SVG,
        "content_html": content_html,
    }

    return _fill_template(template, replacements)


async def render_game_announce(
    announce_item: dict,
    appid: str,
    game_name: str,
    game_logo_url: str,
    canvas_width: int = 720,
) -> bytes:
    """渲染指定游戏的公告卡片为 PNG 图片字节。"""
    html_content = render_game_announce_html(
        announce_item=announce_item,
        appid=appid,
        game_name=game_name,
        game_logo_url=game_logo_url,
        canvas_width=canvas_width,
    )
    return await render_html(
        html_content,
        selector=".announce-container",
        viewport_width=canvas_width + 40,
        viewport_height=1200,
        device_scale_factor=2.0,
    )
