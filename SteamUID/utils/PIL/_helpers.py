import hashlib
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.utils.image.utils import download_pic_to_image

CACHE_DIR: Path = get_res_path("SteamUID") / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_BG_HASH_PATTERN = re.compile(r"/([0-9a-fA-F]{40})/")
_URL_HASH_PATTERN = re.compile(r"[0-9a-fA-F]{40}")


def _truncate_to_width(
    text: str, font: ImageFont.FreeTypeFont, max_width: float
) -> str:
    """截断 text 使 前缀+"…" 不超过 max_width"""
    if font.getlength(text) <= max_width:
        return text
    ellipsis = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.getlength(text[:mid] + ellipsis) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + ellipsis) if lo > 0 else ellipsis


def _font_with_height(target_h: int) -> ImageFont.FreeTypeFont:
    for sz in range(10, 101):
        font = core_font(sz)
        bbox = font.getbbox("测")
        h = bbox[3] - bbox[1]
        if h >= target_h:
            return font
    return core_font(target_h)


async def _load_or_download(url: str, cache_path: Path) -> Image.Image:
    if cache_path.exists():
        return Image.open(cache_path).convert("RGBA")
    img = (await download_pic_to_image(url)).convert("RGBA")
    img.convert("RGB").save(cache_path, format="JPEG")
    return img


def _center_text_x(center_x: int, text: str, font: ImageFont.FreeTypeFont) -> int:
    return center_x - int(font.getlength(text) // 2)


def text_y_for_center(
    center_y: float, font: ImageFont.FreeTypeFont, text: str = "测"
) -> float:
    """计算 draw.text 的 y 坐标，使文字视觉中心位于 center_y"""
    bbox = font.getbbox(text)
    return center_y - (bbox[1] + bbox[3]) / 2


def draw_vertical_gradient(
    canvas: Image.Image,
    width: int,
    height: int,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> None:
    gradient_draw = ImageDraw.Draw(canvas)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = round(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = round(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = round(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        gradient_draw.line([(0, y), (width, y)], fill=(r, g, b, 255))


def cache_path_for_url(url: str, fallback: str | None = None) -> Path:
    """从 URL 中提取 40 位 hex hash 作为缓存文件名，提取失败时用 fallback 或 md5(url)"""
    m = _BG_HASH_PATTERN.search(url)
    if m:
        return CACHE_DIR / f"{m.group(1)}.jpg"
    m = _URL_HASH_PATTERN.search(url)
    if m:
        return CACHE_DIR / f"{m.group(0)}.jpg"
    h = fallback if fallback is not None else hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{h}.jpg"
