import asyncio
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gsuid_core.logger import logger
from gsuid_core.utils.fonts.fonts import core_font

from ._helpers import (
    CACHE_DIR,
    _center_text_x,
    _font_with_height,
    _load_or_download,
    _truncate_to_width,
    cache_path_for_url,
    draw_vertical_gradient,
    text_y_for_center,
)

_DEFAULT_ACHIEVEMENT_ICON = Path(__file__).parent.parent / "texture2d" / "default_icon.jpg"
from ..utils import maybe_hide_steamid

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

    s = 2.0

    bg_cache = cache_path_for_url(game_background, appid)
    bg = await _load_or_download(game_background, bg_cache)
    W_bg = round(bg.width * s)
    H_bg = round(bg.height * s)
    bg = bg.resize((W_bg, H_bg), Image.Resampling.LANCZOS)

    avatar_h = round(85 * s)
    avatar_cache = CACHE_DIR / f"{avatar_hash}.jpg"
    avatar = await _load_or_download(avatar_url, avatar_cache)
    new_w = round(avatar.width * avatar_h / avatar.height)
    avatar = avatar.resize((new_w, avatar_h), Image.Resampling.LANCZOS)

    canvas_h = H_bg + avatar_h
    canvas = Image.new("RGBA", (W_bg, canvas_h))
    draw_vertical_gradient(canvas, W_bg, canvas_h, theme["gradient_top"], theme["gradient_bottom"])

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(bg, (0, 0), bg)
    overlay.paste(avatar, (0, H_bg), avatar)
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)

    max_name_w = W_bg - round(100 * s)
    font_username = core_font(round(25 * s))
    draw.text(
        (round(100 * s), H_bg + round(5 * s)),
        _truncate_to_width(username, font_username, max_name_w),
        font=font_username, fill=theme["username_color"],
    )

    draw.text((round(100 * s), H_bg + round(40 * s)), theme["subtitle"], font=core_font(round(15 * s)), fill=theme["sub_text_color"])

    font_game_st = core_font(round(15 * s))
    draw.text(
        (round(100 * s), H_bg + round(60 * s)),
        _truncate_to_width(game_name, font_game_st, max_name_w),
        font=font_game_st, fill=theme["sub_text_color"],
    )

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

    s = 2.0

    gamer_hash = gamer_img_url.rstrip("/").split("/")[-1]
    gamer_cache = CACHE_DIR / f"{gamer_hash}.jpg"
    gamer_img = await _load_or_download(gamer_img_url, gamer_cache)

    try:
        if not archivement_img_url:
            raise ValueError("archivement_img_url is empty")
        arch_hash = archivement_img_url.rstrip("/").split("/")[-1]
        arch_cache = CACHE_DIR / f"{arch_hash}.jpg"
        archivement_img = await _load_or_download(archivement_img_url, arch_cache)
    except Exception:
        logger.warning(
            f"[SteamUID] 成就图片下载失败，使用默认图标代替: {archivement_img_url}"
        )
        archivement_img = Image.open(_DEFAULT_ACHIEVEMENT_ICON).convert("RGBA")

    W, H = round(600 * s), round(168 * s)
    canvas = Image.new("RGBA", (W, H))
    draw_vertical_gradient(canvas, W, H, gradient_top, gradient_bottom)

    arch_icon_size = round(128 * s)
    archivement_img = archivement_img.resize((arch_icon_size, arch_icon_size), Image.Resampling.LANCZOS)
    canvas.paste(archivement_img, (round(20 * s), round(20 * s)), archivement_img)

    gamer_icon_size = round(48 * s)
    gamer_img = gamer_img.resize((gamer_icon_size, gamer_icon_size), Image.Resampling.LANCZOS)
    canvas.paste(gamer_img, (round(173 * s), round(20 * s)), gamer_img)

    draw = ImageDraw.Draw(canvas)

    font_gamer = _font_with_height(round(42 * s))
    max_gamer_w = W - round(236 * s)
    draw.text(
        (round(236 * s), round(12 * s)),
        _truncate_to_width(gamer_name, font_gamer, max_gamer_w),
        font=font_gamer, fill=username_color,
    )

    # "在 {game_name} 解锁了成就" —— 混色绘制
    font_game_line = _font_with_height(round(20 * s))
    prefix = "在 "
    suffix = " 解锁了成就"
    x_start = round(173 * s)
    y_line = round(73 * s)
    max_game_line_w = W - x_start - font_game_line.getlength(prefix) - font_game_line.getlength(suffix)
    game_name_disp = _truncate_to_width(game_name, font_game_line, max_game_line_w)
    draw.text((x_start, y_line), prefix, font=font_game_line, fill=white)
    offset1 = font_game_line.getlength(prefix)
    draw.text((x_start + offset1, y_line), game_name_disp, font=font_game_line, fill=game_name_color)
    offset2 = font_game_line.getlength(prefix + game_name_disp)
    draw.text((x_start + offset2, y_line), suffix, font=font_game_line, fill=white)

    font_arch_name = _font_with_height(round(25 * s))
    max_arch_name_w = W - round(173 * s)
    draw.text(
        (round(173 * s), round(98 * s)),
        _truncate_to_width(archivement_name, font_arch_name, max_arch_name_w),
        font=font_arch_name, fill=white,
    )

    font_desc = _font_with_height(round(20 * s))
    max_desc_w = W - round(173 * s)
    draw.text(
        (round(173 * s), round(133 * s)),
        _truncate_to_width(archivement_desc, font_desc, max_desc_w),
        font=font_desc, fill=desc_color,
    )

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
_ACH_BAR_BG      = (0x3b, 0x4f, 0x5e, 255)
_ACH_BAR_FILL    = (0x1a, 0x9f, 0xff, 255)
_ACH_BAR_TEXT    = (0xac, 0xd0, 0xf4, 255)


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
    s = 2.0

    A_W = round(505 * s);  B_W = round(485 * s)
    B_x = (A_W - B_W) // 2
    B_radius = C_radius = round(10 * s)
    game_top = round(10 * s);  game_h = round(25 * s)
    prog_gap_top = round(8 * s)
    prog_text_h = round(14 * s)
    prog_gap_mid = round(5 * s)
    prog_bar_h = round(6 * s)
    prog_gap_bot = round(8 * s)
    prog_section_h = prog_gap_top + prog_text_h + prog_gap_mid + prog_bar_h + prog_gap_bot
    sub_top = game_top + game_h + prog_section_h;  sub_h = round(20 * s)
    grid_top = sub_top + sub_h + round(10 * s);  cell = round(100 * s)
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

    # ── 进度条 ──
    n_total = n_unlocked + n_locked
    pct = n_unlocked / n_total if n_total > 0 else 0.0
    font_prog = _font_with_height(prog_text_h)
    prog_left = B_x + round(20 * s)
    prog_right = B_x + B_W - round(20 * s)
    prog_bar_top = game_top + game_h + prog_gap_top + prog_text_h + prog_gap_mid

    prog_label = f"已获得 {n_unlocked} 项成就，共 {n_total} 项"
    pct_label = f"({round(pct * 100)}%)"
    draw.text((prog_left, game_top + game_h + prog_gap_top),
              prog_label, font=font_prog, fill=_ACH_BAR_TEXT)
    pct_x = prog_right - int(font_prog.getlength(pct_label))
    draw.text((pct_x, game_top + game_h + prog_gap_top),
              pct_label, font=font_prog, fill=_ACH_BAR_TEXT)

    bar_radius = max(prog_bar_h // 2, 1)
    draw.rounded_rectangle(
        (prog_left, prog_bar_top, prog_right, prog_bar_top + prog_bar_h),
        radius=bar_radius, fill=_ACH_BAR_BG,
    )
    fill_w = round((prog_right - prog_left) * pct)
    if fill_w > 0:
        draw.rounded_rectangle(
            (prog_left, prog_bar_top, prog_left + fill_w, prog_bar_top + prog_bar_h),
            radius=bar_radius, fill=_ACH_BAR_FILL,
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


# ==================== 绑定列表卡片 ====================

_BIND_BG_TOP     = (0x17, 0x1a, 0x21)
_BIND_BG_BOTTOM  = (0x1b, 0x28, 0x38)
_BIND_PILL_BG: tuple[int, int, int, int]    = (0x2a, 0x47, 0x5e, 255)
_BIND_PILL_BG_ALT: tuple[int, int, int, int] = (0x1e, 0x36, 0x4a, 255)
_BIND_WHITE: tuple[int, int, int, int]      = (0xff, 0xff, 0xff, 255)
_BIND_GRAY: tuple[int, int, int, int]       = (0x8f, 0x98, 0xa0, 255)
_BIND_BLUE: tuple[int, int, int, int]       = (0x66, 0xc0, 0xf4, 255)
_BIND_GREEN: tuple[int, int, int, int]      = (0xa4, 0xd0, 0x07, 255)
_BIND_GOLD: tuple[int, int, int, int]       = (0xf5, 0xa6, 0x23, 255)
_BIND_DIVIDER: tuple[int, int, int, int]    = (0x3d, 0x5c, 0x78, 255)

_BIND_SCALE = 2.0
_BIND_LOGICAL_W = 600
_BIND_PILL_H = 72
_BIND_PILL_RADIUS = 36
_BIND_PILL_PAD_X = 12
_BIND_PILL_PAD_Y = 8
_BIND_AVATAR_SIZE = 48
_BIND_SECTION_GAP = 10
_BIND_TOP_PAD = 16
_BIND_BOTTOM_PAD = 16
_BIND_SECTION_TITLE_H = 28
_BIND_HEADER_H = 44


def _bind_A(v: float) -> int:
    """逻辑像素 -> 实际像素"""
    return round(v * _BIND_SCALE)


def _bind_font_text_height(
    font: ImageFont.FreeTypeFont, text: str = "测"
) -> int:
    bbox = font.getbbox(text)
    return bbox[3] - bbox[1]


async def _bind_load_avatar(
    avatar_url: str, avatar_hash: str, size: int
) -> Image.Image:
    """加载头像并裁切为圆形 RGBA 图片"""
    cache = CACHE_DIR / f"{avatar_hash}.jpg"
    try:
        if avatar_url:
            avatar = await _load_or_download(avatar_url, cache)
        else:
            avatar = Image.new("RGBA", (size, size), _BIND_PILL_BG)
    except Exception:
        avatar = Image.new("RGBA", (size, size), _BIND_PILL_BG)
    # 裁切为正方形
    side = min(avatar.width, avatar.height)
    left = (avatar.width - side) // 2
    top = (avatar.height - side) // 2
    avatar = avatar.crop((left, top, left + side, top + side))
    avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)
    # 生成圆形蒙版
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    circle = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    circle.paste(avatar, (0, 0), mask)
    return circle


def _bind_draw_pill_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    bg_color: tuple[int, int, int, int],
    text_color: tuple[int, int, int, int] = _BIND_WHITE,
) -> None:
    """绘制药丸形状标签"""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=(y1 - y0) // 2, fill=bg_color)
    tw = font.getlength(text)
    tx = x0 + (x1 - x0 - tw) / 2
    ty = text_y_for_center((y0 + y1) / 2, font, text)
    draw.text((tx, ty), text, font=font, fill=text_color)


async def draw_bind_list_photo(
    now_items: list[dict],
    other_items: list[dict],
    *,
    new_bind_steamid: str | None = None,
    unbind_banner: dict | None = None,
) -> Image.Image:
    """
    绘制 Steam 绑定列表卡片。

    参数:
        now_items: 本群绑定列表，每项含 keys:
            steamid64, name, avatar_url, avatar_hash, friend_code, is_main, warning
        other_items: 其他群绑定列表，格式同上
        new_bind_steamid: 新绑定的 steamid64，会在对应项显示"新绑定"标签
        unbind_banner: 解绑横幅信息，含 keys: name, friend_code
    """
    A = _bind_A
    S = _BIND_SCALE

    # 需要显示的分组
    sections: list[tuple[str, list[dict]]] = []
    if now_items:
        sections.append(("本群绑定", now_items))
    if other_items:
        sections.append(("其他绑定", other_items))

    # 计算画布高度
    def _section_h(items: list[dict]) -> int:
        return len(items) * (_BIND_PILL_H + _BIND_PILL_PAD_Y) - _BIND_PILL_PAD_Y

    total_h = _BIND_TOP_PAD + _BIND_HEADER_H + _BIND_SECTION_GAP
    if unbind_banner:
        total_h += 36 + _BIND_SECTION_GAP  # 横幅高度
    if not sections:
        total_h += 40  # 空状态
    else:
        for _, items in sections:
            total_h += _BIND_SECTION_TITLE_H + _BIND_SECTION_GAP
            total_h += _section_h(items) + _BIND_SECTION_GAP * 2
    total_h += _BIND_BOTTOM_PAD

    W_act = A(_BIND_LOGICAL_W)
    H_act = A(total_h)
    canvas = Image.new("RGBA", (W_act, H_act))
    draw = ImageDraw.Draw(canvas)

    # 渐变背景
    draw_vertical_gradient(canvas, W_act, H_act, _BIND_BG_TOP, _BIND_BG_BOTTOM)

    # 字体
    font_header  = core_font(A(22))
    font_name    = core_font(A(18))
    font_id      = core_font(A(12))
    font_label   = core_font(A(11))
    font_section = core_font(A(14))
    font_friend  = core_font(A(14))
    font_banner  = core_font(A(16))

    cur_y = _BIND_TOP_PAD

    # === 顶部标题 ===
    header_text = "Steam 绑定列表"
    hx = (W_act - draw.textlength(header_text, font_header)) / 2
    hy = text_y_for_center(A(cur_y) + A(_BIND_HEADER_H) / 2, font_header, header_text)
    draw.text((hx, hy), header_text, font=font_header, fill=_BIND_WHITE)
    cur_y += _BIND_HEADER_H + _BIND_SECTION_GAP

    # 分割线
    draw.line([(A(20), A(cur_y)), (A(_BIND_LOGICAL_W - 20), A(cur_y))],
              fill=_BIND_DIVIDER, width=A(1))
    cur_y += _BIND_SECTION_GAP

    # === 解绑横幅 ===
    if unbind_banner:
        banner_text = f"{unbind_banner['name']} ({maybe_hide_steamid(unbind_banner['friend_code'])}) 解绑成功"
        bw = draw.textlength(banner_text, font_banner) + A(24)
        bh = A(28)
        bx = (W_act - bw) / 2
        by = A(cur_y)
        _bind_draw_pill_label(
            draw, (round(bx), round(by), round(bx + bw), round(by + bh)),
            banner_text, font_banner, _BIND_BLUE,
        )
        cur_y += 36 + _BIND_SECTION_GAP

    # === 空状态 ===
    if not sections:
        empty_text = "未绑定任何 Steam 账号"
        f_e = core_font(A(14))
        ex = (W_act - draw.textlength(empty_text, f_e)) / 2
        ey = text_y_for_center(A(cur_y) + A(20), f_e, empty_text)
        draw.text((ex, ey), empty_text, font=f_e, fill=_BIND_GRAY)
        return canvas

    # === 分组 ===
    # 预加载所有头像
    all_items = now_items + other_items
    avatar_tasks = {
        item["steamid64"]: _bind_load_avatar(
            item.get("avatar_url", ""),
            item.get("avatar_hash", item["steamid64"]),
            A(_BIND_AVATAR_SIZE),
        )
        for item in all_items
    }
    avatar_map: dict[str, Image.Image] = {}
    for sid, coro in avatar_tasks.items():
        avatar_map[sid] = await coro

    for section_title, items in sections:
        # 分组标题
        sx = A(20)
        sy = text_y_for_center(A(cur_y) + A(_BIND_SECTION_TITLE_H) / 2, font_section, section_title)
        draw.text((sx, sy), section_title, font=font_section, fill=_BIND_BLUE)
        cur_y += _BIND_SECTION_TITLE_H + _BIND_SECTION_GAP

        # 药丸容器
        for i, item in enumerate(items):
            px0 = A(16)
            py0 = A(cur_y)
            px1 = A(_BIND_LOGICAL_W - 16)
            py1 = A(cur_y + _BIND_PILL_H)
            pill_bg = _BIND_PILL_BG if i % 2 == 0 else _BIND_PILL_BG_ALT

            draw.rounded_rectangle(
                (px0, py0, px1, py1), radius=A(_BIND_PILL_RADIUS), fill=pill_bg
            )

            pill_cy = (py0 + py1) / 2

            # 头像
            avatar_act = A(_BIND_AVATAR_SIZE)
            avatar_x = px0 + A(_BIND_PILL_PAD_X)
            avatar_y = round(pill_cy - avatar_act / 2)
            av = avatar_map.get(item["steamid64"])
            if av is None:
                av = Image.new("RGBA", (avatar_act, avatar_act), _BIND_PILL_BG)
            canvas.paste(av, (avatar_x, avatar_y), av)

            text_x = avatar_x + avatar_act + A(10)

            # 两行文字垂直居中
            name_text = item.get("name", "未知用户")
            friend_text = f"({maybe_hide_steamid(item['friend_code'])})"
            steamid_text = f"SteamID: {maybe_hide_steamid(item['steamid64'])}"

            line1_h = _bind_font_text_height(font_name)
            line2_h = _bind_font_text_height(font_id)
            line_gap = A(4)
            block_h = line1_h + line_gap + line2_h
            block_top = pill_cy - block_h / 2

            line1_cy = block_top + line1_h / 2
            line2_cy = block_top + line1_h + line_gap + line2_h / 2

            # 玩家名
            name_y = text_y_for_center(line1_cy, font_name, name_text)
            draw.text((text_x, name_y), name_text, font=font_name, fill=_BIND_WHITE)
            name_w = draw.textlength(name_text, font_name)

            # 好友码
            friend_x = text_x + name_w + A(4)
            friend_y = text_y_for_center(line1_cy, font_friend, friend_text)
            draw.text((friend_x, friend_y), friend_text, font=font_friend, fill=_BIND_GRAY)

            # 标签
            label_x = friend_x + draw.textlength(friend_text, font_friend) + A(6)
            labels: list[tuple[str, tuple]] = []
            if item.get("is_main"):
                labels.append(("主", _BIND_GOLD))
            if item["steamid64"] == new_bind_steamid:
                labels.append(("新绑定", _BIND_GREEN))
            if item.get("warning"):
                labels.append((item["warning"], _BIND_BLUE))

            for label_text, label_color in labels:
                lw = draw.textlength(label_text, font_label) + A(12)
                lh = A(20)
                ly0 = line1_cy - lh / 2
                _bind_draw_pill_label(
                    draw,
                    (round(label_x), round(ly0), round(label_x + lw), round(ly0 + lh)),
                    label_text, font_label, label_color,
                )
                label_x += lw + A(4)

            # SteamID
            id_y = text_y_for_center(line2_cy, font_id, steamid_text)
            draw.text((text_x, id_y), steamid_text, font=font_id, fill=_BIND_GRAY)

            cur_y += _BIND_PILL_H + _BIND_PILL_PAD_Y

        cur_y += _BIND_SECTION_GAP

    return canvas


# ==================== 玩什么推荐卡片 ====================

_PLAY_BG_TOP       = (0x17, 0x1a, 0x21)
_PLAY_BG_BOTTOM    = (0x1b, 0x28, 0x38)
_PLAY_CARD_BG: tuple[int, int, int, int]       = (0x2a, 0x47, 0x5e, 255)
_PLAY_CARD_BG_ALT: tuple[int, int, int, int]   = (0x1e, 0x36, 0x4a, 255)
_PLAY_WHITE: tuple[int, int, int, int]         = (0xff, 0xff, 0xff, 255)
_PLAY_GRAY: tuple[int, int, int, int]          = (0x8f, 0x98, 0xa0, 255)
_PLAY_BLUE: tuple[int, int, int, int]          = (0x66, 0xc0, 0xf4, 255)
_PLAY_PLACEHOLDER: tuple[int, int, int, int]   = (0x3a, 0x4f, 0x5e, 255)
_PLAY_DIVIDER: tuple[int, int, int, int]       = (0x3d, 0x5c, 0x78, 255)

_PLAY_SCALE = 2.0
_PLAY_LOGICAL_W = 600


def _play_A(v: float) -> int:
    """逻辑像素 -> 实际像素"""
    return round(v * _PLAY_SCALE)


def _play_fmt_playtime(minutes: int) -> str:
    """格式化游玩时长"""
    if minutes <= 0:
        return "未游玩"
    if minutes < 60:
        return f"{minutes} 分钟"
    hours = minutes / 60
    if hours < 100:
        return f"{hours:.1f} 小时"
    return f"{round(hours)} 小时"


async def _play_load_cover(
    cover_url: str, appid: str, target_w: int, target_h: int
) -> Image.Image:
    """下载游戏封面并缩放到目标尺寸；失败返回纯色占位图。"""
    if not cover_url:
        return Image.new("RGBA", (target_w, target_h), _PLAY_PLACEHOLDER)
    try:
        cache_path = cache_path_for_url(cover_url, appid)
        img = await _load_or_download(cover_url, cache_path)
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new("RGBA", (target_w, target_h), _PLAY_PLACEHOLDER)
    return img

def _play_paste_rounded_top(
    canvas: Image.Image,
    img: Image.Image,
    pos: tuple[int, int],
    radius: int,
) -> None:
    """将 img 粘贴到 canvas，仅圆角化顶部两角，底部保持直角。"""
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    md.rectangle((0, radius, w, h), fill=255)
    canvas.paste(img, pos, mask)


async def draw_what_to_play(picks: list[dict]) -> Image.Image:
    """
    绘制"今天玩什么"推荐卡片。

    参数:
        picks: [{"appid": str, "name": str, "playtime": int, "cover_url": str}, ...]
               长度 1-3

    返回:
        PIL.Image.Image —— RGBA 画布
    """
    A = _play_A

    # —— 布局常量（逻辑像素）——
    SIDE_PAD       = 20
    CARD_GAP       = 10
    CARD_W         = 180
    CARD_RADIUS    = 10
    COVER_PAD      = 6
    COVER_RADIUS   = 6
    TOP_PAD        = 24
    BOTTOM_PAD     = 24
    TITLE_H        = 40
    SUBTITLE_H     = 20
    TITLE_GAP      = 8
    SECTION_GAP    = 20
    NAME_TOP_PAD   = 10
    NAME_H         = 22
    NAME_PLAY_GAP  = 4
    PLAYTIME_H     = 16
    NAME_BOT_PAD   = 4

    # 派生尺寸
    cover_w = CARD_W - 2 * COVER_PAD          # 168
    cover_h = round(cover_w * 1.5)            # 252 (2:3)
    name_area_h = NAME_TOP_PAD + NAME_H + NAME_PLAY_GAP + PLAYTIME_H + NAME_BOT_PAD  # 56
    card_h = COVER_PAD + cover_h + name_area_h  # 314
    canvas_h = TOP_PAD + TITLE_H + TITLE_GAP + SUBTITLE_H + SECTION_GAP + card_h + BOTTOM_PAD

    W_act = A(_PLAY_LOGICAL_W)
    H_act = A(canvas_h)

    # —— 创建画布 + 渐变背景 ——
    canvas = Image.new("RGBA", (W_act, H_act))
    draw_vertical_gradient(canvas, W_act, H_act, _PLAY_BG_TOP, _PLAY_BG_BOTTOM)
    draw = ImageDraw.Draw(canvas)

    # —— 字体 ——
    font_title    = core_font(A(30))
    font_subtitle = core_font(A(14))
    font_name     = core_font(A(16))
    font_playtime = core_font(A(12))

    # —— 标题 ——
    title_text = "今天玩什么"
    title_x = (W_act - draw.textlength(title_text, font_title)) / 2
    title_y = text_y_for_center(A(TOP_PAD) + A(TITLE_H) / 2, font_title, title_text)
    draw.text((title_x, title_y), title_text, font=font_title, fill=_PLAY_BLUE)

    # —— 副标题 ——
    subtitle_text = "从你的游戏库中随机推荐"
    sub_x = (W_act - draw.textlength(subtitle_text, font_subtitle)) / 2
    sub_y = text_y_for_center(
        A(TOP_PAD + TITLE_H + TITLE_GAP) + A(SUBTITLE_H) / 2,
        font_subtitle, subtitle_text,
    )
    draw.text((sub_x, sub_y), subtitle_text, font=font_subtitle, fill=_PLAY_GRAY)

    # —— 分割线 ——
    divider_y = A(TOP_PAD + TITLE_H + TITLE_GAP + SUBTITLE_H + SECTION_GAP // 2)
    draw.line(
        [(A(SIDE_PAD), divider_y), (A(_PLAY_LOGICAL_W - SIDE_PAD), divider_y)],
        fill=_PLAY_DIVIDER, width=A(1),
    )

    # —— 并发下载封面 ——
    cover_target_w = A(cover_w)
    cover_target_h = A(cover_h)
    covers = await asyncio.gather(
        *[_play_load_cover(
            g["cover_url"], g["appid"], cover_target_w, cover_target_h
        ) for g in picks]
    )

    # —— 绘制卡片 ——
    cards_top = A(TOP_PAD + TITLE_H + TITLE_GAP + SUBTITLE_H + SECTION_GAP)

    for i, game in enumerate(picks):
        cx = A(SIDE_PAD) + A(i * (CARD_W + CARD_GAP))
        cy = cards_top
        cw = A(CARD_W)
        ch = A(card_h)

        # 卡片背景（圆角矩形）
        card_bg = _PLAY_CARD_BG if i % 2 == 0 else _PLAY_CARD_BG_ALT
        draw.rounded_rectangle(
            (cx, cy, cx + cw, cy + ch), radius=A(CARD_RADIUS), fill=card_bg,
        )

        # 封面图（顶部圆角）
        cover = covers[i]
        cover_x = cx + A(COVER_PAD)
        cover_y = cy + A(COVER_PAD)
        _play_paste_rounded_top(canvas, cover, (cover_x, cover_y), A(COVER_RADIUS))

        # 游戏名
        name_text = _truncate_to_width(
            game["name"], font_name, cw - 2 * A(COVER_PAD),
        )
        name_center_x = cx + cw // 2
        name_cy = cover_y + cover_target_h + A(NAME_TOP_PAD) + A(NAME_H) / 2
        name_y = text_y_for_center(name_cy, font_name, name_text)
        draw.text(
            (_center_text_x(name_center_x, name_text, font_name), name_y),
            name_text, font=font_name, fill=_PLAY_WHITE,
        )

        # 游玩时长
        playtime_text = _play_fmt_playtime(game["playtime"])
        playtime_cy = name_cy + A(NAME_H) / 2 + A(NAME_PLAY_GAP) + A(PLAYTIME_H) / 2
        playtime_y = text_y_for_center(playtime_cy, font_playtime, playtime_text)
        draw.text(
            (_center_text_x(name_center_x, playtime_text, font_playtime), playtime_y),
            playtime_text, font=font_playtime, fill=_PLAY_GRAY,
        )

    return canvas
