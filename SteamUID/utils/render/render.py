import asyncio
import base64
import os
import pathlib
import shutil
import tempfile
import time

from gsuid_core.logger import logger

from ..downloader import replace_html_urls_with_local
from ..exceptions import SteamError, SteamRenderError

_DEFAULT_ICON_PATH = pathlib.Path(__file__).parent.parent / "texture2d" / "default_icon.jpg"

# 默认游戏封面 Base64 SVG (深蓝Steam配色)
_DEFAULT_GAME_COVER_SVG = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMzIiIGhlaWdodD0iODciIHZpZXdCb3g9IjAgMCAyMzIgODciPjxyZWN0IHdpZHRoPSIyMzIiIGhlaWdodD0iODciIGZpbGw9IiMxYjI4MzgiLz48dGV4dCB4PSI1MCUiIHk9IjUwJSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZmlsbD0iIzY3YzFmNSIgZm9udC1mYW1pbHk9InNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiIGZvbnQtd2VpZ2h0PSJib2xkIj5TVEVBTTwvdGV4dD48L3N2Zz4="
)


def _get_default_icon_b64() -> str:
    """读取默认问号头像并转为 Base64 Data URL"""
    if _DEFAULT_ICON_PATH.exists():
        return "data:image/jpeg;base64," + base64.b64encode(_DEFAULT_ICON_PATH.read_bytes()).decode()
    return ""


def _fill_template(template: str, replacements: dict[str, str]) -> str:
    """用 str.replace 替换所有 {{key}} 占位符。"""
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", value)
    return template


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
        html_content = await replace_html_urls_with_local(html_content)
    except Exception as e:
        logger.warning(f"[SteamUID - 渲染] 预处理本地化静态资源异常，降级使用原 HTML: {e}")

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

            # 等待所有图片加载完成，确保元素高度计算准确、避免长图被截断
            try:
                await page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('img')).every(img => img.complete)",
                    timeout=15000,
                )
                await page.wait_for_timeout(200)
            except Exception:
                pass  # 图片加载超时降级

            # 截图指定元素
            # 使用 page.screenshot(clip=精确浮点 bbox) 替代 element.screenshot()，
            # 避免 element.screenshot() 在 sub-pixel 高度时向上取整到下一个整数，
            # 导致底部多出 1px 透明区域露出 body 的白色背景。
            element = page.locator(selector)
            await element.wait_for(state="visible")
            bbox = await element.bounding_box()
            if bbox is None:
                raise SteamError("无法获取目标元素位置")

            # 若元素高度超出当前视口高度，动态扩展视口大小以保证完整长图内容不会被截断
            needed_height = int(bbox["y"] + bbox["height"] + 50)
            if needed_height > viewport_height:
                await page.set_viewport_size({"width": viewport_width, "height": needed_height})
                await page.wait_for_timeout(100)
                bbox = await element.bounding_box()
                if bbox is None:
                    raise SteamError("无法获取目标元素位置")

            screenshot_bytes = await page.screenshot(
                clip={
                    "x": bbox["x"],
                    "y": bbox["y"],
                    "width": bbox["width"],
                    "height": bbox["height"],
                },
                type="png",
            )

            await browser.close()
            return screenshot_bytes
    except SteamError:
        raise
    except Exception as e:
        logger.exception(f"[SteamUID - 渲染] Playwright 渲染 HTML 失败: {e!r}")
        raise SteamRenderError("Playwright 渲染 HTML 发生错误，详情请查看后台。")


def draw_page_badge(img_bytes: bytes, page_idx: int, total_pages: int) -> bytes:
    """在图片右下角绘制页码角标（如 1/5）。"""
    import io
    from PIL import Image, ImageDraw, ImageFont

    im = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    badge_text = f"{page_idx}/{total_pages}"

    font_size = 24
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(im)
    bbox = draw.textbbox((0, 0), badge_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x, pad_y = 16, 8
    badge_w = tw + pad_x * 2
    badge_h = th + pad_y * 2

    x2 = im.width - 24
    y2 = im.height - 24
    x1 = x2 - badge_w
    y1 = y2 - badge_h

    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ol_draw = ImageDraw.Draw(overlay)
    ol_draw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=6,
        fill=(15, 23, 36, 220),
        outline=(103, 193, 245, 140),
        width=1,
    )
    ol_draw.text((x1 + pad_x, y1 + pad_y - 2), badge_text, fill=(255, 255, 255, 250), font=font)

    res = Image.alpha_composite(im, overlay).convert("RGB")
    buf = io.BytesIO()
    res.save(buf, format="PNG")
    return buf.getvalue()


async def render_html_multipage(
    html_content: str,
    selector: str,
    *,
    split_selector: str = ".announce-header, .announce-content > *, .card-footer",
    max_page_pixel_height: int = 5000,
    viewport_width: int = 492,
    viewport_height: int = 600,
    device_scale_factor: float = 2.0,
) -> list[bytes]:
    """支持超长图智能元素级分割与多页渲染。

    当渲染后的实际像素高度超过 max_page_pixel_height（默认 5000px）时，
    会以元素分界线为切点进行精准无损分割，并在每张图片的右下角标注页码（如 1/5）。
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise SteamError("playwright 库未安装，此功能无法使用")

    try:
        html_content = await replace_html_urls_with_local(html_content)
    except Exception as e:
        logger.warning(f"[SteamUID - 渲染] 预处理本地化静态资源异常，降级使用原 HTML: {e}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=device_scale_factor,
            )
            page = await context.new_page()

            # 注入 HTML 并等待网络就绪
            await page.set_content(html_content, wait_until="networkidle")

            # 自动检测并等待视频就绪
            has_video = await page.evaluate("!!document.querySelector('video')")
            if has_video:
                try:
                    await page.wait_for_function(
                        "document.querySelector('video')?.readyState >= 2",
                        timeout=5000,
                    )
                    await page.evaluate("""
                        const v = document.querySelector('video');
                        if (v && v.duration > 1) { v.currentTime = 1; }
                    """)
                    await page.wait_for_timeout(500)
                except Exception:
                    pass

            # 等待所有图片加载完成
            try:
                await page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('img')).every(img => img.complete)",
                    timeout=20000,
                )
                await page.wait_for_timeout(200)
            except Exception:
                pass

            element = page.locator(selector)
            await element.wait_for(state="visible")
            bbox = await element.bounding_box()
            if bbox is None:
                raise SteamError("无法获取目标元素位置")

            total_css_height = bbox["height"]
            total_pixel_height = total_css_height * device_scale_factor

            # 动态扩展视口大小
            needed_height = int(bbox["y"] + total_css_height + 50)
            if needed_height > viewport_height:
                await page.set_viewport_size({"width": viewport_width, "height": needed_height})
                await page.wait_for_timeout(100)
                bbox = await element.bounding_box()
                if bbox is None:
                    raise SteamError("无法获取目标元素位置")

            # 判断是否需要分页切割
            if total_pixel_height <= max_page_pixel_height:
                screenshot_bytes = await page.screenshot(
                    clip={
                        "x": bbox["x"],
                        "y": bbox["y"],
                        "width": bbox["width"],
                        "height": bbox["height"],
                    },
                    type="png",
                )
                await browser.close()
                return [screenshot_bytes]

            # 获取所有分界子元素的位置
            elements_bounds = await page.evaluate(f"""() => {{
                const container = document.querySelector('{selector}');
                if (!container) return [];
                const containerTop = container.getBoundingClientRect().top;
                const nodes = Array.from(document.querySelectorAll('{split_selector}'));
                return nodes.map(el => {{
                    const r = el.getBoundingClientRect();
                    return {{
                        top: r.top - containerTop,
                        bottom: r.bottom - containerTop,
                        height: r.height
                    }};
                }}).filter(b => b.height > 0);
            }}""")

            max_css_per_page = max_page_pixel_height / device_scale_factor
            slices = []
            curr_start = 0.0

            while curr_start < total_css_height - 10:
                target_end = curr_start + max_css_per_page
                if target_end >= total_css_height:
                    slices.append((curr_start, total_css_height))
                    break

                # 寻找在 target_end 之前结束的最后一个元素的 bottom
                valid_bottoms = [
                    b["bottom"]
                    for b in elements_bounds
                    if curr_start < b["bottom"] <= target_end
                ]
                if valid_bottoms:
                    split_y = max(valid_bottoms)
                else:
                    split_y = target_end

                slices.append((curr_start, split_y))
                curr_start = split_y

            total_pages = len(slices)
            results: list[bytes] = []

            for idx, (s, e) in enumerate(slices):
                clip_rect = {
                    "x": bbox["x"],
                    "y": bbox["y"] + s,
                    "width": bbox["width"],
                    "height": e - s,
                }
                page_bytes = await page.screenshot(clip=clip_rect, type="png")
                if total_pages > 1:
                    page_bytes = draw_page_badge(page_bytes, idx + 1, total_pages)
                results.append(page_bytes)

            await browser.close()
            return results
    except SteamError:
        raise
    except Exception as e:
        logger.exception(f"[SteamUID - 渲染] Playwright 渲染 HTML 失败: {e!r}")
        raise SteamRenderError("Playwright 渲染 HTML 发生错误，详情请查看后台。")



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
        html_content = await replace_html_urls_with_local(html_content)
    except Exception as e:
        logger.warning(f"[SteamUID - 渲染] 预处理本地化静态资源异常，降级使用原 HTML: {e}")

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
            logger.error(
                f"[SteamUID - 渲染] ffmpeg 转换 GIF 失败: {stderr.decode(errors='replace')}"
            )
            raise SteamRenderError("ffmpeg 转换 GIF 发生错误，详情请查看后台。")

        # 读取 GIF 字节
        with open(gif_path, "rb") as f:
            gif_bytes = f.read()

        return gif_bytes

    except SteamError:
        raise
    except Exception as e:
        logger.exception(f"[SteamUID - 渲染] Playwright 渲染 GIF 失败: {e!r}")
        raise SteamRenderError("Playwright 渲染 GIF 发生错误，详情请查看后台。")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
