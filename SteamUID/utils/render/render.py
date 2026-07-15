import pathlib
from typing import Any

from playwright.async_api import async_playwright

_TEMPLATE_PATH = pathlib.Path(__file__).parent / "html" / "steam_miniprofile.html"


# ============================================================
# 通用渲染：HTML → PNG 截图
# ============================================================

async def render_html(
    html_content: str,
    selector: str,
    *,
    viewport_width: int = 492,
    viewport_height: int = 600,
) -> bytes:
    """通用 HTML 渲染：将 HTML 字符串注入浏览器并截图指定元素。

    自动检测 <video> 元素并等待其就绪。

    参数:
        html_content: 完整的 HTML 字符串
        selector: 要截图的 CSS 选择器（如 ".miniprofile_container"）
        viewport_width: 浏览器视口宽度
        viewport_height: 浏览器视口高度

    返回:
        PNG 格式的图片字节数据
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=1,
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
