import re
from pathlib import Path

from PIL import Image, ImageDraw
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.utils.image.utils import download_pic_to_image

CACHE_DIR: Path = get_res_path("steamUID") / "imgs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_BG_HASH_PATTERN = re.compile(r"/([0-9a-fA-F]{40})/")


async def _load_or_download(url: str, cache_path: Path) -> Image.Image:
    if cache_path.exists():
        return Image.open(cache_path).convert("RGBA")
    img = (await download_pic_to_image(url)).convert("RGBA")
    img.convert("RGB").save(cache_path, format="JPEG")
    return img


async def draw_start_game_photo(
        appid: str,
        game_name: str,
        avatar_url: str,
        avatar_hash: str,
        username: str,
        game_background: str | None = None,
) -> Image.Image | None:
    if game_background is None:
        return None
    # 颜色常量
    gradient_top = (0x30, 0x4E, 0x41)      # 画布背景上方 #304E41
    gradient_bottom = (0x1D, 0x27, 0x2D)   # 画布背景下方 #1D272D
    username_color = (0xCE, 0xE8, 0xB1)    # 用户名 #CEE8B1
    sub_text_color = (0x90, 0xBA, 0x3C)    # "正在玩" / 游戏名 #90BA3C
    # 背景
    m = _BG_HASH_PATTERN.search(game_background)
    if m:
        bg_cache = CACHE_DIR / f"{m.group(1)}.jpg"
    else:
        bg_cache = CACHE_DIR / f"{appid}.jpg"
    bg = await _load_or_download(game_background, bg_cache)
    # 画布
    W_bg, H_bg = bg.size
    # 玩家
    avatar_cache = CACHE_DIR / f"{avatar_hash}.jpg"
    avatar = await _load_or_download(avatar_url, avatar_cache)
    new_w = round(avatar.width * 85 / avatar.height)
    avatar = avatar.resize((new_w, 85), Image.Resampling.LANCZOS)

    # 画布背景：上方渐变到下方
    canvas_h = H_bg + 85
    canvas = Image.new("RGBA", (W_bg, canvas_h))
    gradient_draw = ImageDraw.Draw(canvas)
    for y in range(canvas_h):
        ratio = y / max(canvas_h - 1, 1)
        r = round(gradient_top[0] + (gradient_bottom[0] - gradient_top[0]) * ratio)
        g = round(gradient_top[1] + (gradient_bottom[1] - gradient_top[1]) * ratio)
        b = round(gradient_top[2] + (gradient_bottom[2] - gradient_top[2]) * ratio)
        gradient_draw.line([(0, y), (W_bg, y)], fill=(r, g, b, 255))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(bg, (0, 0), bg)
    overlay.paste(avatar, (0, H_bg), avatar)
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    draw.text((100, H_bg + 5), username, font=core_font(25), fill=username_color)
    draw.text((100, H_bg + 40), "正在玩", font=core_font(15), fill=sub_text_color)
    draw.text((100, H_bg + 60), game_name, font=core_font(15), fill=sub_text_color)

    return canvas


async def draw_end_game_photo(
        appid: str,
        game_name: str,
        avatar_url: str,
        avatar_hash: str,
        username: str,
        game_background: str | None = None,
) -> Image.Image | None:
    if game_background is None:
        return None
    # 颜色常量
    gradient_top = (0x26, 0x4C, 0x5E)      # 画布背景上方 #264C5E
    gradient_bottom = (0x1C, 0x22, 0x2B)   # 画布背景下方 #1C222B
    username_color = (0x65, 0xC6, 0xF0)    # 用户名 #65C6F0
    sub_text_color = (0x39, 0x68, 0x7E)    # "已结束游玩" / 游戏名 #39687E
    # 背景
    m = _BG_HASH_PATTERN.search(game_background)
    if m:
        bg_cache = CACHE_DIR / f"{m.group(1)}.jpg"
    else:
        bg_cache = CACHE_DIR / f"{appid}.jpg"
    bg = await _load_or_download(game_background, bg_cache)
    # 画布
    W_bg, H_bg = bg.size
    # 玩家
    avatar_cache = CACHE_DIR / f"{avatar_hash}.jpg"
    avatar = await _load_or_download(avatar_url, avatar_cache)
    new_w = round(avatar.width * 85 / avatar.height)
    avatar = avatar.resize((new_w, 85), Image.Resampling.LANCZOS)

    # 画布背景：上方渐变到下方
    canvas_h = H_bg + 85
    canvas = Image.new("RGBA", (W_bg, canvas_h))
    gradient_draw = ImageDraw.Draw(canvas)
    for y in range(canvas_h):
        ratio = y / max(canvas_h - 1, 1)
        r = round(gradient_top[0] + (gradient_bottom[0] - gradient_top[0]) * ratio)
        g = round(gradient_top[1] + (gradient_bottom[1] - gradient_top[1]) * ratio)
        b = round(gradient_top[2] + (gradient_bottom[2] - gradient_top[2]) * ratio)
        gradient_draw.line([(0, y), (W_bg, y)], fill=(r, g, b, 255))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(bg, (0, 0), bg)
    overlay.paste(avatar, (0, H_bg), avatar)
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    draw.text((100, H_bg + 5), username, font=core_font(25), fill=username_color)
    draw.text((100, H_bg + 40), "已结束游玩", font=core_font(15), fill=sub_text_color)
    draw.text((100, H_bg + 60), game_name, font=core_font(15), fill=sub_text_color)

    return canvas

