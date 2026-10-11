from __future__ import annotations

import time
import shutil
import asyncio
import tempfile
from typing import TYPE_CHECKING
from pathlib import Path

import jinja2

from gsuid_core.logger import logger

if TYPE_CHECKING:
    from playwright.async_api import Page, Browser, FloatRect, Playwright

_HTML_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = _HTML_DIR / "templates"
STYLE_DIR = _HTML_DIR / "styles"

_TAG = "[Steam·图片渲染]"

# 元素超出视口时截图会被裁切：撑大视口后留出的安全边距与重排等待
_VIEWPORT_MARGIN = 50
_REFLOW_WAIT_MS = 100

# 低配机器上省掉 GPU 进程与多余渲染进程，实测单个实例省 20MB 左右
_LAUNCH_ARGS = [
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--renderer-process-limit=1",
]

# 闲置超过 TTL 后连 driver 一起释放，把常驻内存还回基线；空闲巡检间隔 30s
_IDLE_TTL = 120.0
_REAP_INTERVAL = 30.0
# 浏览器复用上限：chromium 长跑内存缓慢上涨，到量换新实例
_MAX_BROWSER_USES = 200

# GIF：暂停视频后逐帧 seek，单帧 seek 等待上限与最小时长
_GIF_SEEK_TIMEOUT_MS = 2000
_GIF_MIN_SECONDS = 1.0

_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=False,
)

_playwright: Playwright | None = None
_browser: Browser | None = None
_browser_uses = 0
_last_used = 0.0
_browser_lock = asyncio.Lock()
_reaper: asyncio.Task[None] | None = None


def read_styles(*names: str) -> str:
    """按顺序读取 styles 目录下的样式并拼接，文件缺失直接报错以暴露拼写问题。"""
    return "\n".join((STYLE_DIR / name).read_text(encoding="utf-8") for name in names)


def get_template(name: str) -> jinja2.Template:
    """获取 templates 目录下的模板对象。"""
    return _ENV.get_template(name)


async def _shutdown() -> None:
    """释放浏览器与 playwright driver；调用方需持有 _browser_lock。"""
    global _playwright, _browser, _browser_uses
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None
    _browser_uses = 0


async def _get_browser() -> Browser:
    """取常驻浏览器：driver 懒启动、掉线自愈、复用超上限换新；调用方需持有 _browser_lock。"""
    global _playwright, _browser, _browser_uses
    if _playwright is None:
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()

    if _browser is not None and (not _browser.is_connected() or _browser_uses >= _MAX_BROWSER_USES):
        if _browser.is_connected():
            await _browser.close()
        _browser = None

    if _browser is None:
        _browser = await _playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        _browser_uses = 0

    _browser_uses += 1
    return _browser


async def _reap_when_idle() -> None:
    """空闲超过 TTL 时释放浏览器与 driver，让常驻内存回到基线。"""
    global _reaper
    while True:
        await asyncio.sleep(_REAP_INTERVAL)
        async with _browser_lock:
            if time.monotonic() - _last_used < _IDLE_TTL:
                continue
            await _shutdown()
        break
    _reaper = None


def _ensure_reaper() -> None:
    """首次渲染后拉起空闲回收协程，进程内只保留一个。"""
    global _reaper
    if _reaper is None or _reaper.done():
        _reaper = asyncio.create_task(_reap_when_idle())


async def render_html(
    html_content: str,
    selector: str,
    *,
    viewport_width: int = 800,
    viewport_height: int = 600,
    device_scale_factor: float = 2.0,
    quality: int = 85,
    timeout: float = 25.0,
) -> bytes:
    """统一 HTML 渲染入口：按 css 选择器截取目标元素并返回 JPEG 字节。

    浏览器常驻复用、空闲超时自动释放，渲染串行以保证低配机器不被并发拖垮。

    Args:
        html_content: 完整 HTML 文档字符串。
        selector: 截图目标的 css 选择器。
        viewport_width: 初始视口宽度，目标超宽时自动撑大。
        viewport_height: 初始视口高度，目标超高时自动撑大。
        device_scale_factor: 设备像素比，决定出图清晰度。
        quality: JPEG 质量，取值 1-100。
        timeout: 页面加载与元素等待的单步超时秒数。

    Returns:
        截图产出的 JPEG 字节。
    """
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    except ImportError as exc:
        raise RuntimeError("playwright 未安装，无法渲染图片") from exc

    global _last_used
    timeout_ms = int(timeout * 1000)
    _ensure_reaper()

    async with _browser_lock:
        _last_used = time.monotonic()
        try:
            browser = await _get_browser()
            page = await browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=device_scale_factor,
            )
            try:
                page.set_default_timeout(timeout_ms)
                page.set_default_navigation_timeout(timeout_ms)

                await page.set_content(html_content, wait_until="load", timeout=timeout_ms)
                # 图片直链走本地服务，等全部 img 加载完再截图，避免截到半张图
                await page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('img')).every((img) => img.complete)",
                    timeout=timeout_ms,
                )

                element = page.locator(selector)
                await element.wait_for(state="visible")
                box = await element.bounding_box()
                if box is None:
                    raise RuntimeError(f"截取目标不可见: {selector}")

                needed_width = int(box["x"] + box["width"]) + _VIEWPORT_MARGIN
                needed_height = int(box["y"] + box["height"]) + _VIEWPORT_MARGIN
                if needed_width > viewport_width or needed_height > viewport_height:
                    await page.set_viewport_size(
                        {
                            "width": max(viewport_width, needed_width),
                            "height": max(viewport_height, needed_height),
                        }
                    )
                    await page.wait_for_timeout(_REFLOW_WAIT_MS)
                    box = await element.bounding_box()
                    if box is None:
                        raise RuntimeError(f"截取目标不可见: {selector}")

                return await page.screenshot(
                    clip={
                        "x": box["x"],
                        "y": box["y"],
                        "width": box["width"],
                        "height": box["height"],
                    },
                    type="jpeg",
                    quality=quality,
                )
            finally:
                await page.close()
        except (PlaywrightTimeoutError, TimeoutError) as exc:
            logger.warning(f"{_TAG} 渲染超时: {exc!r}")
            raise RuntimeError("渲染超时，请稍后重试") from exc
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception(f"{_TAG} 渲染失败: {exc!r}")
            raise RuntimeError("渲染图片时发生错误，请查看后台日志") from exc


async def render_html_gif(
    html_content: str,
    selector: str,
    *,
    viewport_width: int = 800,
    viewport_height: int = 600,
    fps: int = 10,
    max_seconds: float = 3.0,
    timeout: float = 25.0,
) -> bytes:
    """渲染 HTML 并把目标元素的动画输出为 GIF。

    复用常驻浏览器：暂停视频后逐帧 seek 截元素，省掉实时录屏与二次裁剪；
    无 <video> 时按同一帧率采样，兼容 GIF / WebP 动态素材。
    """
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg 未安装，无法渲染 GIF") from exc
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    except ImportError as exc:
        raise RuntimeError("playwright 未安装，无法渲染图片") from exc

    ffmpeg_exe = get_ffmpeg_exe()
    timeout_ms = int(timeout * 1000)
    global _last_used
    _ensure_reaper()

    tmp_dir = Path(tempfile.mkdtemp(prefix="steam_gif_"))
    frames: list[bytes] = []
    try:
        async with _browser_lock:
            _last_used = time.monotonic()
            browser = await _get_browser()
            page = await browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=1,
            )
            try:
                page.set_default_timeout(timeout_ms)
                page.set_default_navigation_timeout(timeout_ms)
                await page.set_content(html_content, wait_until="load", timeout=timeout_ms)
                # 图片直链走本地服务，等全部加载完再取帧，避免截到半张图
                await page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('img')).every((img) => img.complete)",
                    timeout=timeout_ms,
                )
                element = page.locator(selector)
                await element.wait_for(state="visible")
                box = await element.bounding_box()
                if box is None:
                    raise RuntimeError(f"截取目标不可见: {selector}")
                has_video = bool(await page.evaluate("() => !!document.querySelector('video')"))
                seconds = await _gif_seconds(page, has_video, max_seconds)
                frame_count = max(1, int(round(seconds * fps)))
                frames = await _capture_frames(page, box, has_video, frame_count, fps)
            except (PlaywrightTimeoutError, TimeoutError) as exc:
                logger.warning(f"{_TAG} 渲染 GIF 超时: {exc!r}")
                raise RuntimeError("渲染超时，请稍后重试") from exc
            except RuntimeError:
                raise
            except Exception as exc:
                logger.exception(f"{_TAG} 渲染 GIF 失败: {exc!r}")
                raise RuntimeError("渲染 GIF 时发生错误，请查看后台日志") from exc
            finally:
                await page.close()

        return await _encode_gif(ffmpeg_exe, tmp_dir, frames, fps)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _gif_seconds(page: Page, has_video: bool, max_seconds: float) -> float:
    """GIF 时长：有视频取视频时长，否则按上限；钳制在最小与上限之间。"""
    seconds = max_seconds
    if has_video:
        await page.wait_for_function(
            "() => { const v = document.querySelector('video'); return !!v && v.readyState >= 2; }",
            timeout=_GIF_SEEK_TIMEOUT_MS,
        )
        raw: object = await page.evaluate(
            "() => { const v = document.querySelector('video'); return (v && isFinite(v.duration)) ? v.duration : 0; }"
        )
        if isinstance(raw, (int, float)) and raw > 0:
            seconds = min(float(raw), max_seconds)
    return max(_GIF_MIN_SECONDS, seconds)


async def _capture_frames(
    page: Page,
    box: FloatRect,
    has_video: bool,
    frame_count: int,
    fps: int,
) -> list[bytes]:
    """逐帧截取目标元素；有视频时先暂停再按帧 seek，保证帧可复现。"""
    if has_video:
        await page.evaluate("() => { const v = document.querySelector('video'); if (v) v.pause(); }")

    frames: list[bytes] = []
    for index in range(frame_count):
        if has_video:
            await _seek_video(page, index / fps)
        else:
            await page.wait_for_timeout(int(1000 / fps))
        frames.append(
            await page.screenshot(
                clip={
                    "x": box["x"],
                    "y": box["y"],
                    "width": box["width"],
                    "height": box["height"],
                },
                type="png",
            )
        )
    return frames


async def _seek_video(page: Page, seconds: float) -> None:
    """把视频 seek 到指定时间并等 seeked；未触发 seeked 时靠定时器兜底。"""
    await page.evaluate(
        "(t) => new Promise((resolve) => {"
        " const v = document.querySelector('video');"
        " if (!v) { resolve(true); return; }"
        " let done = false;"
        " const finish = () => {"
        "   if (done) { return; }"
        "   done = true;"
        "   v.removeEventListener('seeked', finish);"
        "   resolve(true);"
        " };"
        " v.addEventListener('seeked', finish);"
        " v.currentTime = t;"
        " setTimeout(finish, 300);"
        "})",
        seconds,
    )


async def _encode_gif(
    ffmpeg_exe: str,
    tmp_dir: Path,
    frames: list[bytes],
    fps: int,
) -> bytes:
    """把 PNG 帧序列交给 ffmpeg 合成 GIF，调色板优化以压体积。"""
    for index, frame in enumerate(frames):
        (tmp_dir / f"frame_{index:03d}.png").write_bytes(frame)

    gif_path = tmp_dir / "output.gif"
    filter_complex = "[0:v]split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5"
    process = await asyncio.create_subprocess_exec(
        ffmpeg_exe,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(tmp_dir / "frame_%03d.png"),
        "-filter_complex",
        filter_complex,
        "-loop",
        "0",
        str(gif_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(f"{_TAG} ffmpeg 合成 GIF 失败: {stderr.decode(errors='replace')}")
        raise RuntimeError("合成 GIF 时发生错误，请查看后台日志")
    return gif_path.read_bytes()
