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
    text_y_for_center,
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
        banner_text = f"{unbind_banner['name']} ({unbind_banner['friend_code']}) 解绑成功"
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
            friend_text = f"({item['friend_code']})"
            steamid_text = f"SteamID: {item['steamid64']}"

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
