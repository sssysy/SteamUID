import asyncio
from math import ceil

from PIL import Image, ImageDraw, ImageFont
from gsuid_core.utils.fonts.fonts import core_font

from ._helpers import (
    CACHE_DIR,
    _center_text_x,
    _font_with_height,
    _load_or_download,
    _truncate_to_width,
    cache_path_for_url,
    draw_vertical_gradient,
)

_GAME_STATUS_THEMES: dict[str, dict] = {
    "start": {
        "gradient_top":    (0x30, 0x4E, 0x41),
        "gradient_bottom": (0x1D, 0x27, 0x2D),
        "username_color":  (0xCE, 0xE8, 0xB1),
        "sub_text_color":  (0x90, 0xBA, 0x3C),
        "subtitle":        "正在玩",
    },
    "end": {
        "gradient_top":    (0x26, 0x4C, 0x5E),
        "gradient_bottom": (0x1C, 0x22, 0x2B),
        "username_color":  (0x65, 0xC6, 0xF0),
        "sub_text_color":  (0x39, 0x68, 0x7E),
        "subtitle":        "已结束游玩",
    },
}


async def draw_game_status_photo(
    *,
    appid: str,
    game_name: str,
    avatar_url: str,
    avatar_hash: str,
    username: str,
    game_background: str | None = None,
    is_playing: bool = True,
) -> Image.Image | None:
    if game_background is None:
        return None
    theme = _GAME_STATUS_THEMES["start" if is_playing else "end"]

    bg_cache = cache_path_for_url(game_background, appid)
    bg = await _load_or_download(game_background, bg_cache)
    W_bg, H_bg = bg.size

    avatar_cache = CACHE_DIR / f"{avatar_hash}.jpg"
    avatar = await _load_or_download(avatar_url, avatar_cache)
    new_w = round(avatar.width * 85 / avatar.height)
    avatar = avatar.resize((new_w, 85), Image.Resampling.LANCZOS)

    canvas_h = H_bg + 85
    canvas = Image.new("RGBA", (W_bg, canvas_h))
    draw_vertical_gradient(canvas, W_bg, canvas_h, theme["gradient_top"], theme["gradient_bottom"])

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(bg, (0, 0), bg)
    overlay.paste(avatar, (0, H_bg), avatar)
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    draw.text((100, H_bg + 5), username, font=core_font(25), fill=theme["username_color"])
    draw.text((100, H_bg + 40), theme["subtitle"], font=core_font(15), fill=theme["sub_text_color"])
    draw.text((100, H_bg + 60), game_name, font=core_font(15), fill=theme["sub_text_color"])

    return canvas


async def draw_archivements_photo(
        gamer_name: str,
        gamer_img_url: str,
        archivement_name: str,
        archivement_img_url: str,
        game_name: str,
        archivement_desc: str,
) -> Image.Image:
    username_color = (0xCE, 0xE8, 0xB1)
    game_name_color = (0x90, 0xBA, 0x3C)
    white = (0xFF, 0xFF, 0xFF)
    desc_color = (0xAA, 0xAA, 0xAA)
    gradient_top = (0x26, 0x4C, 0x5E)
    gradient_bottom = (0x1C, 0x22, 0x2B)

    gamer_hash = gamer_img_url.rstrip("/").split("/")[-1]
    gamer_cache = CACHE_DIR / f"{gamer_hash}.jpg"
    gamer_img = await _load_or_download(gamer_img_url, gamer_cache)

    if not archivement_img_url:
        raise ValueError("archivement_img_url is empty")

    arch_hash = archivement_img_url.rstrip("/").split("/")[-1]
    arch_cache = CACHE_DIR / f"{arch_hash}.jpg"
    archivement_img = await _load_or_download(archivement_img_url, arch_cache)

    W, H = 600, 168
    canvas = Image.new("RGBA", (W, H))
    draw_vertical_gradient(canvas, W, H, gradient_top, gradient_bottom)

    archivement_img = archivement_img.resize((128, 128), Image.Resampling.LANCZOS)
    canvas.paste(archivement_img, (20, 20), archivement_img)

    gamer_img = gamer_img.resize((48, 48), Image.Resampling.LANCZOS)
    canvas.paste(gamer_img, (173, 20), gamer_img)

    draw = ImageDraw.Draw(canvas)

    font_gamer = _font_with_height(42)
    draw.text((236, 12), gamer_name, font=font_gamer, fill=username_color)

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

    font_arch_name = _font_with_height(25)
    draw.text((173, 98), archivement_name, font=font_arch_name, fill=white)

    font_desc = _font_with_height(20)
    draw.text((173, 133), archivement_desc, font=font_desc, fill=desc_color)

    return canvas


_ACH_BG_B        = (0x1b, 0x28, 0x38)
_ACH_BG_C        = (0x2a, 0x47, 0x5e)
_ACH_SUBTITLE    = (0x66, 0xc0, 0xf4)
_ACH_NAME        = (0xff, 0xff, 0xff)
_ACH_NAME_LOCKED = (0xb0, 0xb0, 0xb0)
_ACH_DESC        = (0x8f, 0x98, 0xa0)
_ACH_GAME_NAME   = (0xff, 0xff, 0xff)
_ACH_PLACEHOLDER = (0x3a, 0x4f, 0x5e, 0xff)
_ACH_COLS        = 4


async def _safe_load_ach_icon(
    url: str, size: int, grayscale: bool = False
) -> Image.Image:
    if not url:
        return Image.new("RGBA", (size, size), _ACH_PLACEHOLDER)
    cache_path = cache_path_for_url(url)
    try:
        img = await _load_or_download(url, cache_path)
    except Exception:
        return Image.new("RGBA", (size, size), _ACH_PLACEHOLDER)
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    if grayscale:
        alpha = img.getchannel("A") if img.mode == "RGBA" else None
        img = img.convert("L").convert("RGBA")
        if alpha is not None:
            img.putalpha(alpha)
    return img.resize((size, size), Image.Resampling.LANCZOS)


async def draw_archivement_info(
    game_name: str,
    unlocked_list: list[tuple[str, str, str]],
    locked_list: list[tuple[str, str, str]] | None = None,
) -> Image.Image:
    """绘制 Steam 风格成就列表，未解锁成就另起一行渲染"""
    s = 1.0

    A_W = round(505 * s);  B_W = round(485 * s)
    B_x = (A_W - B_W) // 2
    B_radius = C_radius = round(10 * s)
    game_top = round(10 * s);  game_h = round(25 * s)
    sub_top = game_top + game_h + round(10 * s);  sub_h = round(20 * s)
    grid_top = round(80 * s);  cell = round(100 * s)
    col_gap = row_gap = round(15 * s)
    grid_left_pad = round(20 * s);  grid_bottom_pad = round(15 * s)
    icon_size = round(48 * s);  icon_top_pad = round(8 * s)
    name_h = round(14 * s);  desc_h = round(10 * s)
    text_gap = round(3 * s);  text_h_pad = round(4 * s)

    locked_list = locked_list or []
    n_unlocked = len(unlocked_list)
    n_locked = len(locked_list)
    R_unlocked = ceil(n_unlocked / _ACH_COLS) if n_unlocked else 0
    R_locked = ceil(n_locked / _ACH_COLS) if n_locked else 0
    R = R_unlocked + R_locked
    grid_h = R * cell + (R - 1) * row_gap if R else 0
    B_H = A_H = grid_top + grid_h + grid_bottom_pad

    font_game = _font_with_height(game_h)
    font_sub = _font_with_height(sub_h)
    font_name = _font_with_height(name_h)
    font_desc = _font_with_height(desc_h)

    icons_unlocked = (await asyncio.gather(
        *[_safe_load_ach_icon(t[0], icon_size, grayscale=False)
          for t in unlocked_list]
    )) if unlocked_list else []
    icons_locked = (await asyncio.gather(
        *[_safe_load_ach_icon(t[0], icon_size, grayscale=False)
          for t in locked_list]
    )) if locked_list else []

    canvas = Image.new("RGBA", (A_W, A_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (B_x, 0, B_x + B_W, B_H), radius=B_radius, fill=_ACH_BG_B + (255,)
    )

    B_center_x = B_x + B_W // 2
    game_max_w = B_W - 2 * round(20 * s)

    game_disp = _truncate_to_width(game_name, font_game, game_max_w)
    draw.text(
        (_center_text_x(B_center_x, game_disp, font_game), game_top),
        game_disp, font=font_game, fill=_ACH_GAME_NAME,
    )

    sub_text = "游戏成就列表"
    draw.text(
        (_center_text_x(B_center_x, sub_text, font_sub), sub_top),
        sub_text, font=font_sub, fill=_ACH_SUBTITLE,
    )

    if R == 0:
        empty = "暂无成就数据"
        f_e = _font_with_height(round(16 * s))
        draw.text(
            (_center_text_x(B_center_x, empty, f_e), grid_top + round(10 * s)),
            empty, font=f_e, fill=_ACH_DESC,
        )
        return canvas

    text_max_w = cell - 2 * text_h_pad

    def _render_cell(
        idx_in_segment: int, row_offset: int, icon: Image.Image,
        name: str, desc: str, name_color: tuple,
    ) -> None:
        col = idx_in_segment % _ACH_COLS
        row = row_offset + idx_in_segment // _ACH_COLS
        cx = B_x + grid_left_pad + col * (cell + col_gap)
        cy = grid_top + row * (cell + row_gap)

        draw.rounded_rectangle(
            (cx, cy, cx + cell, cy + cell), radius=C_radius, fill=_ACH_BG_C + (255,)
        )

        ix = cx + (cell - icon_size) // 2
        iy = cy + icon_top_pad
        canvas.paste(icon, (ix, iy), icon)

        icon_bottom = iy + icon_size
        region_h = (cy + cell) - icon_bottom
        block_h = name_h + text_gap + desc_h
        name_top = icon_bottom + (region_h - block_h) // 2
        desc_top = name_top + name_h + text_gap
        ccx = cx + cell // 2

        name_disp = _truncate_to_width(name, font_name, text_max_w)
        desc_disp = _truncate_to_width(desc, font_desc, text_max_w)
        draw.text(
            (_center_text_x(ccx, name_disp, font_name), name_top),
            name_disp, font=font_name, fill=name_color,
        )
        draw.text(
            (_center_text_x(ccx, desc_disp, font_desc), desc_top),
            desc_disp, font=font_desc, fill=_ACH_DESC,
        )

    for i, (url, name, desc) in enumerate(unlocked_list):
        _render_cell(i, 0, icons_unlocked[i], name, desc, _ACH_NAME)
    for i, (url, name, desc) in enumerate(locked_list):
        _render_cell(i, R_unlocked, icons_locked[i], name, desc, _ACH_NAME_LOCKED)

    return canvas
