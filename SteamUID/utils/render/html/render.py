from __future__ import annotations

import time
import asyncio
from typing import TYPE_CHECKING
from pathlib import Path

import jinja2

from gsuid_core.logger import logger

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright

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
