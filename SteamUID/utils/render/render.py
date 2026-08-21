import io
import pathlib
import os
import time
import asyncio
import tempfile
import shutil
from typing import Any
from ..exceptions import SteamError


_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "steam_miniprofile.html"
_GAME_STATUS_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "game_status.html"
_STEAM_INFO_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "steam_info.html"
_GAME_RANKING_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "game_ranking.html"
_USER_RANKING_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "user_ranking.html"
_GAME_RECOMMEND_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "game_recommend.html"
_BIND_LIST_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "bind_list.html"
_STEAM_WALL_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "steam_wall.html"




# ============================================================
# 通用渲染：HTML → PNG 截图
# ============================================================

async def render_html(
    html_content: str,
    selector: str,
    *,
    viewport_width: int = 492,
    viewport_height: int = 600,
    device_scale_factor: float = 2.0,
) -> bytes:
    """通用 HTML 渲染：将 HTML 字符串注入浏览器并截图指定元素。

    自动检测 <video> 元素并等待其就绪。

    参数:
        html_content: 完整的 HTML 字符串
        selector: 要截图的 CSS 选择器（如 ".miniprofile_container"）
        viewport_width: 浏览器视口宽度
        viewport_height: 浏览器视口高度
        device_scale_factor: 缩放倍率（默认 2.0 渲染高清图）

    返回:
        PNG 格式的图片字节数据
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise SteamError("playwright 库未安装，此功能无法使用")


    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=device_scale_factor,
            )
            page = await context.new_page()

            # 注入 HTML，等待网络资源加载完成
            await page.set_content(html_content, wait_until="networkidle")

            # 自动检测并等待视频就绪
            has_video = await page.evaluate("!!document.querySelector('video')")
            if has_video:
                try:
                    await page.wait_for_function(
                        "document.querySelector('video')?.readyState >= 2",
                        timeout=5000,
                    )
                    # seek 到 1 秒处获取更具代表性的帧
                    await page.evaluate("""
                        const v = document.querySelector('video');
                        if (v && v.duration > 1) { v.currentTime = 1; }
                    """)
                    await page.wait_for_timeout(500)
                except Exception:
                    pass  # 视频加载超时降级

            # 截图指定元素
            element = page.locator(selector)
            screenshot_bytes = await element.screenshot(type="png")

            await browser.close()
            return screenshot_bytes
    except Exception as e:
        raise SteamError(f"Playwright 渲染 HTML 失败: {e}")


# ============================================================
# 通用渲染：HTML → GIF 动画（Playwright 录制 + ffmpeg 转换）
# ============================================================

async def render_html_gif(
    html_content: str,
    selector: str,
    *,
    viewport_width: int = 492,
    viewport_height: int = 600,
) -> bytes:
    """录制页面视频并转换为 GIF。

    当页面包含动态内容（背景视频、GIF 头像、动态头像框）时使用。
    通过 Playwright 录制页面视频，再用 ffmpeg 裁剪并转换为 GIF。

    参数:
        html_content: 完整的 HTML 字符串
        selector: 要录制的 CSS 选择器（如 ".miniprofile_container"）
        viewport_width: 浏览器视口宽度
        viewport_height: 浏览器视口高度

    返回:
        GIF 格式的图片字节数据
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise SteamError("playwright 库未安装，此功能无法使用")

    try:
        from imageio_ffmpeg import get_ffmpeg_exe  # type: ignore[import-not-found]
    except ImportError:
        raise SteamError("imageio-ffmpeg 库未安装，此功能无法使用")

    ffmpeg_exe = get_ffmpeg_exe()
    tmp_dir = tempfile.mkdtemp(prefix="steam_gif_")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=1,
                record_video_dir=tmp_dir,
            )
            page = await context.new_page()

            # 获取视频录制保存路径（需在关闭 context 前获取）
            video_path = await page.video.path()  # type: ignore[union-attr]

            # 记录加载开始时间（视频录制从页面创建即开始，需跳过加载阶段）
            load_start = time.monotonic()

            # 注入 HTML，等待网络资源加载完成
            await page.set_content(html_content, wait_until="networkidle")

            # 等待所有图片加载完成（GIF 头像/头像框/徽章图标等）
            try:
                await page.wait_for_function(
                    "Array.from(document.querySelectorAll('img'))"
                    ".every(img => img.complete && img.naturalHeight > 0)",
                    timeout=10000,
                )
            except Exception:
                pass  # 超时降级，部分图片可能加载失败但不阻塞录制

            # 检测 <video> 元素并获取时长
            has_video = await page.evaluate("!!document.querySelector('video')")
            if has_video:
                try:
                    await page.wait_for_function(
                        "document.querySelector('video')?.readyState >= 2",
                        timeout=5000,
                    )
                except Exception:
                    pass  # 超时降级，使用默认时长
                duration = await page.evaluate(
                    "(() => {"
                    "  const v = document.querySelector('video');"
                    "  const d = (v && v.duration && isFinite(v.duration)) ? v.duration : 3;"
                    "  return Math.max(d, 1);"
                    "})()"
                )
            else:
                duration = 3.0

            # 获取目标元素的 bounding box（用于 ffmpeg crop）
            element = page.locator(selector)
            bbox = await element.bounding_box()
            if not bbox:
                raise SteamError("无法获取目标元素位置")

            # 等待 500ms 确保渲染稳定后再开始有效录制
            await page.wait_for_timeout(500)
            seek_offset = time.monotonic() - load_start

            # 录制 duration 秒
            await page.wait_for_timeout(int(duration * 1000))

            # 关闭 context 以保存视频文件
            await context.close()
            await browser.close()

        # ffmpeg 裁剪 + 转 GIF（palette 优化）
        crop_w = int(round(bbox["width"]))
        crop_h = int(round(bbox["height"]))
        crop_x = int(round(bbox["x"]))
        crop_y = int(round(bbox["y"]))

        gif_path = os.path.join(tmp_dir, "output.gif")
        filter_complex = (
            f"[0:v]fps=10,crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
            f"split[s0][s1];"
            f"[s0]palettegen=stats_mode=diff[p];"
            f"[s1][p]paletteuse=dither=bayer:bayer_scale=5"
        )

        process = await asyncio.create_subprocess_exec(
            ffmpeg_exe,
            "-y",
            "-i", str(video_path),
            "-ss", f"{seek_offset:.3f}",
            "-t", f"{duration:.3f}",
            "-filter_complex", filter_complex,
            gif_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise SteamError(
                f"ffmpeg 转换 GIF 失败: {stderr.decode(errors='replace')}"
            )

        # 读取 GIF 字节
        with open(gif_path, "rb") as f:
            gif_bytes = f.read()

        return gif_bytes

    except SteamError:
        raise
    except Exception as e:
        raise SteamError(f"Playwright 渲染 GIF 失败: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# Miniprofile：构建 HTML
# ============================================================

def _build_avatar_frame_html(url: str | None) -> str:
    """构建头像框 HTML 块。无头像框时返回空字符串。"""
    if not url:
        return ""
    return f'<div class="playersection_avatar_frame"><img src="{url}"></div>'


def _build_background_inner_html(
    webm: str | None,
    mp4: str | None,
    img: str | None,
) -> str:
    """构建背景内容 HTML 块。

    优先级：视频(webm/mp4) > 静态图片 > 空字符串
    """
    if webm or mp4:
        sources = ""
        if webm:
            sources += f'<source src="{webm}" type="video/webm">'
        if mp4:
            sources += f'<source src="{mp4}" type="video/mp4">'
        return (
            '<video class="miniprofile_nameplate" playsinline autoplay muted loop>'
            f"{sources}</video>"
        )
    if img:
        return f'<img class="miniprofile_nameplate" src="{img}">'
    return ""


def _build_featured_badge_html(
    icon_url: str | None,
    name: str | None,
    xp: str | None,
) -> str:
    """构建特色徽章 HTML 块。无徽章图标时返回空字符串。"""
    if not icon_url:
        return ""
    name_html = f'<div class="name">{name}</div>' if name else ""
    xp_html = f'<div class="xp">{xp} 点经验值</div>' if xp else ""
    return (
        '<div class="miniprofile_featuredcontainer">'
        f'<img src="{icon_url}" class="badge_icon">'
        f'<div class="description">{name_html}{xp_html}</div>'
        "</div>"
    )


def _fill_template(template: str, replacements: dict[str, str]) -> str:
    """用 str.replace 替换所有 {{key}} 占位符。"""
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", value)
    return template


_FIELD_DEFAULTS: dict[str, Any] = {
    "avatar_url": "", # 头像 URL
    "avatar_frame_url": None, # 头像框 URL
    "background_video_webm": None, # 背景视频 webm URL
    "background_video_mp4": None, # 背景视频 mp4 URL
    "background_image_url": None, # 背景图片 URL
    "persona_name": "", # 个人名称
    "persona_class": "online", # 个人状态类名
    "status_class": "online", # 状态类名
    "status_text": "在线", # 状态文本
    "border_color_class": "border_color_online", # 边框颜色类名
    "level_num": "0", # 等级
    "level_classes": "lvl_0", # 等级类名
    "badge_icon_url": None, # 特色徽章图标 URL
    "badge_name": None, # 特色徽章名称
    "badge_xp": None, # 特色徽章经验值
}


def render_miniprofile(data: Any) -> str:
    """迷你个人资料卡片"""
    # 1. 从 data 中读取所有字段
    fields = {k: getattr(data, k, v) for k, v in _FIELD_DEFAULTS.items()}

    # 2. 读取 HTML 模板
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")

    # 3. 构建条件 HTML 块
    avatar_frame_html = _build_avatar_frame_html(fields["avatar_frame_url"])
    background_inner_html = _build_background_inner_html(
        fields["background_video_webm"],
        fields["background_video_mp4"],
        fields["background_image_url"],
    )
    featured_badge_html = _build_featured_badge_html(
        fields["badge_icon_url"], fields["badge_name"], fields["badge_xp"]
    )

    # 4. 组装替换字典
    replacements: dict[str, str] = {
        "avatar_url": fields["avatar_url"],
        "persona_name": fields["persona_name"],
        "persona_class": fields["persona_class"],
        "status_class": fields["status_class"],
        "status_text": fields["status_text"],
        "border_color_class": fields["border_color_class"],
        "level_num": fields["level_num"],
        "level_classes": fields["level_classes"],
        "avatar_frame_html": avatar_frame_html,
        "background_inner_html": background_inner_html,
        "featured_badge_html": featured_badge_html,
    }

    # 5. 替换占位符并返回
    return _fill_template(template, replacements)


_GS_THEMES: dict[str, dict] = {
    "start": {
        "status_bar_color": "#5cbe32",
        "persona_color":    "#e1e1e1",
        "group_color":      "#8f98a0",
        "subtitle_color":   "#808a94",
        "subtitle":         "正在玩",
        "game_name_color":  "#90ba3c",
    },
    "end": {
        "status_bar_color": "#57cbde",
        "persona_color":    "#57cbde",
        "group_color":      "#4c91ac",
        "subtitle_color":   "#808a94",
        "subtitle":         "已结束游玩",
        "game_name_color":  "#57cbde",
    },
}

_GS_DEFAULT_W = 460
_GS_DEFAULT_H_BG = 215
_GS_INFO_ROW_H = 84


import base64

_DEFAULT_ICON_PATH = pathlib.Path(__file__).parent.parent / "texture2d" / "default_icon.jpg"


def _get_default_icon_b64() -> str:
    """读取默认问号头像并转为 Base64 Data URL"""
    if _DEFAULT_ICON_PATH.exists():
        return "data:image/jpeg;base64," + base64.b64encode(_DEFAULT_ICON_PATH.read_bytes()).decode()
    return ""


def render_game_status_html(
    *,
    username: str,
    game_name: str,
    avatar_url: str,
    avatar_frame_url: str | None = None,
    game_background: str | None = None,
    is_playing: bool = True,
    group_name: str | None = None,
) -> str:
    """构建游戏状态（开始/结束游戏）卡片的 HTML 字符串。"""
    theme_key = "start" if is_playing else "end"
    theme = _GS_THEMES[theme_key]

    template = _GAME_STATUS_TEMPLATE_PATH.read_text(encoding="utf-8")

    if game_background:
        cover_html = f'<img class="cover-img" src="{game_background}" alt="">'
        cover_h_val = str(_GS_DEFAULT_H_BG)
    else:
        cover_html = ""
        cover_h_val = "0"

    avatar_frame_html = (
        f'<div class="avatar-frame"><img src="{avatar_frame_url}" alt=""></div>'
        if avatar_frame_url
        else ""
    )

    default_avatar = _get_default_icon_b64()
    avatar_src = avatar_url if avatar_url else default_avatar
    group_name_html = f'<span class="group-name">({group_name})</span>' if group_name else ""

    replacements = {
        "canvas_width": str(_GS_DEFAULT_W),
        "cover_height": cover_h_val,
        "cover_html": cover_html,
        "avatar_url": avatar_src,
        "avatar_frame_html": avatar_frame_html,
        "default_avatar": default_avatar,
        "status_bar_color": theme["status_bar_color"],
        "persona_color": theme["persona_color"],
        "group_color": theme["group_color"],
        "subtitle_color": theme["subtitle_color"],
        "persona_name": username,
        "group_name_html": group_name_html,
        "subtitle": theme["subtitle"],
        "game_name": game_name,
        "game_name_color": theme["game_name_color"],
    }

    return _fill_template(template, replacements)


async def render_game_status(
    *,
    username: str,
    game_name: str,
    avatar_url: str,
    avatar_frame_url: str | None = None,
    game_background: str | None = None,
    is_playing: bool = True,
    group_name: str | None = None,
) -> bytes:
    """渲染游戏开始/结束状态卡片为 PNG 字节。"""
    html_content = render_game_status_html(
        username=username,
        game_name=game_name,
        avatar_url=avatar_url,
        avatar_frame_url=avatar_frame_url,
        game_background=game_background,
        is_playing=is_playing,
        group_name=group_name,
    )
    total_h = (_GS_DEFAULT_H_BG if game_background else 0) + _GS_INFO_ROW_H + 50
    return await render_html(
        html_content,
        ".game-status-card",
        viewport_width=_GS_DEFAULT_W + 50,
        viewport_height=total_h,
        device_scale_factor=2.0,
    )


# ============================================================
# Steam 信息卡片渲染
# ============================================================

_STEAM_INFO_FIELD_DEFAULTS: dict[str, Any] = {
    "avatar_url": "",
    "avatar_frame_url": None,
    "background_image_url": None,
    "persona_name": "",
    "status_class": "online",
    "status_text": "在线",
    "badge_icon_url": None,
    "bio_text": "",
    "level_num": "0",
    "level_classes": "lvl_0",
    "region": "未知",
    "account_age": "--",
    "account_value": "0",
    "playtime_hours": "0",
    "game_count": "0",
    "steam_id_display": "",
}


def render_steam_info_html(data: Any) -> str:
    """构建 Steam 信息卡片的 HTML 字符串。"""
    fields = {k: getattr(data, k, v) for k, v in _STEAM_INFO_FIELD_DEFAULTS.items()}
    template = _STEAM_INFO_TEMPLATE_PATH.read_text(encoding="utf-8")

    # 构建头像框 HTML
    avatar_frame_html = ""
    if fields["avatar_frame_url"]:
        avatar_frame_html = f'<div class="avatar_frame"><img src="{fields["avatar_frame_url"]}" alt=""></div>'

    # 构建徽章图标 HTML
    badge_icon_html = ""
    if fields["badge_icon_url"]:
        badge_icon_html = f'<img class="badge_icon" src="{fields["badge_icon_url"]}" alt="">'

    # 构建个人简介 HTML
    bio_html = ""
    if fields["bio_text"]:
        bio_html = f'<div class="profile_summary">{fields["bio_text"]}</div>'

    # 构建背景 HTML
    background_html = ""
    if fields["background_image_url"]:
        background_html = f'<img class="background_image" src="{fields["background_image_url"]}" alt="">'

    replacements = {
        "avatar_url": fields["avatar_url"],
        "avatar_frame_html": avatar_frame_html,
        "background_html": background_html,
        "persona_name": fields["persona_name"],
        "badge_icon_html": badge_icon_html,
        "status_class": fields["status_class"],
        "status_text": fields["status_text"],
        "bio_html": bio_html,
        "level_num": str(fields["level_num"]),
        "level_classes": fields["level_classes"],
        "region": fields["region"],
        "account_age": str(fields["account_age"]),
        "account_value": str(fields["account_value"]),
        "playtime_hours": str(fields["playtime_hours"]),
        "game_count": str(fields["game_count"]),
        "steam_id_display": str(fields["steam_id_display"]),
    }

    return _fill_template(template, replacements)


async def render_steam_info(data: Any) -> bytes:
    """渲染 Steam 信息卡片为 PNG 字节。"""
    html_content = render_steam_info_html(data)
    return await render_html(
        html_content,
        ".steam_info_card",
        viewport_width=820,
        viewport_height=420,
        device_scale_factor=2.0,
    )


# ============================================================
# Steam 群游戏排行榜渲染
# ============================================================

# 默认游戏封面 Base64 SVG (深蓝Steam配色)
_DEFAULT_GAME_COVER_SVG = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMzIiIGhlaWdodD0iODciIHZpZXdCb3g9IjAgMCAyMzIgODciPjxyZWN0IHdpZHRoPSIyMzIiIGhlaWdodD0iODciIGZpbGw9IiMxYjI4MzgiLz48dGV4dCB4PSI1MCUiIHk9IjUwJSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZmlsbD0iIzY3YzFmNSIgZm9udC1mYW1pbHk9InNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiIGZvbnQtd2VpZ2h0PSJib2xkIj5TVEVBTTwvdGV4dD48L3N2Zz4="
)


def format_ranking_duration(seconds: int | float) -> str:
    """按要求格式化游玩时长：
    - 不足1h的按分钟显示，如 59.8min、0.0min
    - 超过或等于1h的按小时显示，如 112.3h、1.0h
    - 最大到h，不需要统计到天
    """
    if seconds < 0:
        seconds = 0
    if seconds < 3600:
        minutes = seconds / 60.0
        return f"{minutes:.1f}min"
    else:
        hours = seconds / 3600.0
        return f"{hours:.1f}h"


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
    import html as html_lib

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
    est_height = 80 + item_count * 58 + 50
    return await render_html(
        html_content,
        ".ranking-container",
        viewport_width=canvas_w + 50,
        viewport_height=max(est_height, 200),
        device_scale_factor=2.0,
    )


# ============================================================
# Steam 群用户游玩时长排行榜渲染
# ============================================================

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
    import html as html_lib

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
    est_height = 80 + item_count * 58 + 50
    return await render_html(
        html_content,
        ".ranking-container",
        viewport_width=canvas_w + 50,
        viewport_height=max(est_height, 200),
        device_scale_factor=2.0,
    )


# ============================================================
# Steam 库存游戏推荐（玩什么）渲染
# ============================================================

def render_game_recommend_html(
    games_data: list[dict],
    canvas_width: int = 880,
) -> str:
    """构建 Steam 库存游戏推荐（玩什么）卡片的 HTML 字符串。

    games_data item 字典格式:
        - appid: str | int
        - name: str
        - description: str (游戏简介)
        - cover_url: str (横板封面 URL，可选)
    """
    import html as html_lib

    template = _GAME_RECOMMEND_TEMPLATE_PATH.read_text(encoding="utf-8")
    title_text = "steam 库存游戏推荐"

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
        "cards_html": cards_html,
    }

    return _fill_template(template, replacements)


async def render_game_recommend(
    games_data: list[dict],
) -> bytes:
    """渲染 Steam 库存游戏推荐卡片为 PNG 字节。"""
    canvas_w = 880
    html_content = render_game_recommend_html(games_data, canvas_width=canvas_w)
    return await render_html(
        html_content,
        ".recommend-container",
        viewport_width=canvas_w + 50,
        viewport_height=550,
        device_scale_factor=2.0,
    )


# ============================================================
# Steam 绑定列表卡片渲染
# ============================================================

def render_bind_list_html(
    bind_items: list[dict],
    user_name: str = "",
    user_id: str = "",
    qq_avatar_url: str | None = None,
    canvas_width: int = 560,
) -> str:
    """构建 Steam 绑定列表卡片的 HTML 字符串。

    bind_items 列表项格式:
        - steamid64: str
        - name: str (Steam 昵称)
        - avatar_url: str (Steam 头像 URL)
        - avatar_frame_url: str | None (Steam 头像框 URL)
        - bg_url: str | None (Steam 迷你资料背景 URL)
        - friend_code: str (Steam 好友码)
        - is_main: bool (是否为本群主账号)
    """
    import html as html_lib

    template = _BIND_LIST_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_avatar = _get_default_icon_b64()

    # QQ 头像
    if not qq_avatar_url:
        uid = str(user_id)
        if uid.isdigit():
            qq_avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={uid}&s=640"
        else:
            qq_avatar_url = default_avatar

    display_user_name = html_lib.escape(user_name or user_id or "用户")

    items_html_parts = []
    if not bind_items:
        items_html = '<div class="empty-state">未绑定任何 Steam 账号</div>'
    else:
        for item in bind_items:
            name = html_lib.escape(item.get("name", "未知用户"))
            friend_code = html_lib.escape(str(item.get("friend_code", "")))
            avatar_url = item.get("avatar_url") or default_avatar
            avatar_frame_url = item.get("avatar_frame_url")
            bg_url = item.get("bg_url")
            is_main = bool(item.get("is_main", False))

            main_class = " is-main" if is_main else ""

            bg_style = f' style="background-image: url(\'{bg_url}\');"' if bg_url else ""
            bg_html = f'<div class="pill-bg"{bg_style}></div>' if bg_url else ""

            frame_html = ""
            if avatar_frame_url:
                frame_html = f'<div class="avatar-frame"><img src="{avatar_frame_url}" onerror="this.parentElement.style.display=\'none\'" alt=""></div>'

            item_html = (
                f'<div class="pill-item{main_class}">'
                f'  {bg_html}'
                f'  <div class="pill-mask"></div>'
                f'  <div class="pill-content">'
                f'    <div class="avatar-box">'
                f'      <img class="steam-avatar" src="{avatar_url}" onerror="this.onerror=null;this.src=\'{default_avatar}\'" alt="">'
                f'      {frame_html}'
                f'    </div>'
                f'    <div class="info-box">'
                f'      <div class="steam-name" title="{name}">{name}</div>'
                f'      <div class="steam-friend-code">{friend_code}</div>'
                f'    </div>'
                f'  </div>'
                f'</div>'
            )
            items_html_parts.append(item_html)
        items_html = "\n".join(items_html_parts)

    replacements = {
        "canvas_width": str(canvas_width),
        "qq_avatar_url": qq_avatar_url,
        "default_avatar": default_avatar,
        "user_name": display_user_name,
        "items_html": items_html,
    }

    return _fill_template(template, replacements)


async def render_bind_list(
    bind_items: list[dict],
    user_name: str = "",
    user_id: str = "",
    qq_avatar_url: str | None = None,
    canvas_width: int = 560,
) -> bytes:
    """渲染 Steam 绑定列表卡片为 PNG 字节。"""
    html_content = render_bind_list_html(
        bind_items=bind_items,
        user_name=user_name,
        user_id=user_id,
        qq_avatar_url=qq_avatar_url,
        canvas_width=canvas_width,
    )
    item_count = max(len(bind_items), 1)
    est_height = 140 + item_count * 86 + 60
    return await render_html(
        html_content,
        ".bind-card",
        viewport_width=canvas_width + 40,
        viewport_height=est_height,
        device_scale_factor=2.0,
    )


# ============================================================
# Steam 游戏墙卡片渲染
# ============================================================

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
    import html as html_lib

    template = _STEAM_WALL_TEMPLATE_PATH.read_text(encoding="utf-8")
    default_avatar = _get_default_icon_b64()

    # 1. 顶部用户卡片
    user_name = html_lib.escape(user_data.get("name", "未知用户"))
    friend_code = html_lib.escape(str(user_data.get("friend_code", "")))
    avatar_url = user_data.get("avatar_url") or default_avatar
    avatar_frame_url = user_data.get("avatar_frame_url")
    bg_url = user_data.get("bg_url")

    bg_style = f' style="background-image: url(\'{bg_url}\');"' if bg_url else ""
    bg_html = f'<div class="pill-bg"{bg_style}></div>' if bg_url else ""

    frame_html = ""
    if avatar_frame_url:
        frame_html = (
            f'<div class="avatar-frame"><img src="{avatar_frame_url}" '
            f'onerror="this.parentElement.style.display=\'none\'" alt=""></div>'
        )

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
        "user_name": user_name,
        "friend_code": friend_code,
        "avatar_url": avatar_url,
        "frame_html": frame_html,
        "bg_html": bg_html,
        "default_avatar": default_avatar,
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
    est_height = max(600, 140 + int(valid_count * 30))

    return await render_html(
        html_content,
        ".steam-wall-card",
        viewport_width=canvas_width + 40,
        viewport_height=est_height,
        device_scale_factor=2.0,
    )







