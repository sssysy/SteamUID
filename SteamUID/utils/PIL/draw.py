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

    canvas = Image.new("RGBA", (W_bg, H_bg + 85), (0x1D, 0x1E, 0x23, 255))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(bg, (0, 0), bg)
    overlay.paste(avatar, (0, H_bg), avatar)
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    draw.text((100, H_bg + 10), username, font=core_font(25), fill=(0xCE, 0xE8, 0xB1))
    draw.text((100, H_bg + 40), "正在玩", font=core_font(15), fill=(0x90, 0xBA, 0x3C))
    draw.text((100, H_bg + 60), game_name, font=core_font(15), fill=(0x90, 0xBA, 0x3C))

    return canvas
