import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.utils.image.utils import download_pic_to_image

CACHE_DIR: Path = get_res_path("SteamUID") / "imgs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_BG_HASH_PATTERN = re.compile(r"/([0-9a-fA-F]{40})/")


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

async def draw_archivements_photo(
        gamer_name: str,
        gamer_img_url: str,
        archivement_name: str,
        archivement_img_url: str,
        game_name: str,
        archivement_desc: str,
) -> Image.Image:
    # 颜色常量（参照 draw_start_game_photo / draw_end_game_photo）
    username_color = (0xCE, 0xE8, 0xB1)      # 用户名 #CEE8B1
    game_name_color = (0x90, 0xBA, 0x3C)     # 游戏名 #90BA3C
    white = (0xFF, 0xFF, 0xFF)                # 其他文字白色
    desc_color = (0xAA, 0xAA, 0xAA)          # 描述文字灰色
    gradient_top = (0x26, 0x4C, 0x5E)        # 画布背景上方 #264C5E
    gradient_bottom = (0x1C, 0x22, 0x2B)     # 画布背景下方 #1C222B

    # 下载/缓存图片
    gamer_hash = gamer_img_url.rstrip("/").split("/")[-1]
    gamer_cache = CACHE_DIR / f"{gamer_hash}.jpg"
    gamer_img = await _load_or_download(gamer_img_url, gamer_cache)

    if not archivement_img_url:
        raise ValueError("archivement_img_url is empty")

    arch_hash = archivement_img_url.rstrip("/").split("/")[-1]
    arch_cache = CACHE_DIR / f"{arch_hash}.jpg"
    archivement_img = await _load_or_download(archivement_img_url, arch_cache)
    # 画布
    W, H = 600, 168
    canvas = Image.new("RGBA", (W, H))
    gradient_draw = ImageDraw.Draw(canvas)
    for y in range(H):
        ratio = y / max(H - 1, 1)
        r = round(gradient_top[0] + (gradient_bottom[0] - gradient_top[0]) * ratio)
        g = round(gradient_top[1] + (gradient_bottom[1] - gradient_top[1]) * ratio)
        b = round(gradient_top[2] + (gradient_bottom[2] - gradient_top[2]) * ratio)
        gradient_draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # 成就图标
    archivement_img = archivement_img.resize((128, 128), Image.Resampling.LANCZOS)
    canvas.paste(archivement_img, (20, 20), archivement_img)

    # 玩家头像
    gamer_img = gamer_img.resize((48, 48), Image.Resampling.LANCZOS)
    canvas.paste(gamer_img, (173, 20), gamer_img)

    draw = ImageDraw.Draw(canvas)

    # 玩家名
    font_gamer = _font_with_height(48)
    draw.text((236, 15), gamer_name, font=font_gamer, fill=username_color)

    # "在 {game_name} 解锁了成就" —— 混色绘制
    font_game_line = _font_with_height(20)
    prefix = "在 "
    suffix = " 解锁了成就"
    x_start = 173
    draw.text((x_start, 73), prefix, font=font_game_line, fill=white)
    offset1 = font_game_line.getlength(prefix)
    draw.text((x_start + offset1, 73), game_name, font=font_game_line, fill=game_name_color)
    offset2 = font_game_line.getlength(prefix + game_name)
    draw.text((x_start + offset2, 73), suffix, font=font_game_line, fill=white)

    # 成就名称
    font_arch_name = _font_with_height(25)
    draw.text((173, 98), archivement_name, font=font_arch_name, fill=white)

    # 成就描述
    font_desc = _font_with_height(20)
    draw.text((173, 133), archivement_desc, font=font_desc, fill=desc_color)

    return canvas