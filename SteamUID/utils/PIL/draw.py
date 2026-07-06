import asyncio
import hashlib
import re
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.utils.image.utils import download_pic_to_image

CACHE_DIR: Path = get_res_path("SteamUID") / "imgs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_BG_HASH_PATTERN = re.compile(r"/([0-9a-fA-F]{40})/")
# 头像 URL 中的 40 位 hex（不要求两端斜杠），用于推导缓存文件名
_URL_HASH_PATTERN = re.compile(r"[0-9a-fA-F]{40}")


def _truncate_to_width(
    text: str, font: ImageFont.FreeTypeFont, max_width: float
) -> str:
    """截断 text 使 ``前缀 + "…"`` 不超过 max_width，极端窄宽时返回 ``"…"``。"""
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

    # 成就名称
    font_arch_name = _font_with_height(25)
    draw.text((173, 98), archivement_name, font=font_arch_name, fill=white)

    # 成就描述
    font_desc = _font_with_height(20)
    draw.text((173, 133), archivement_desc, font=font_desc, fill=desc_color)

    return canvas

async def draw_user_info_head(
        img: Image.Image,
        user_avatar: str,
        user_name: str,
        user_status: str,
        game_name: str | None = None,
) -> Image.Image:
    # Step 1 — 状态映射与参数校验（先校验，避免无效下载）
    if user_status == "offline":
        username_color = (158, 158, 158)   # #9E9E9E
        subtitle_text = "离线"
        subtitle_color = (89, 89, 89)      # #595959
    elif user_status == "ingame":
        username_color = (206, 232, 177)   # #CEE8B1
        subtitle_text = game_name if game_name else "游戏中"
        subtitle_color = (144, 186, 60)    # #90BA3C
    elif user_status == "online":
        username_color = (101, 198, 240)   # #65C6F0
        subtitle_text = "在线"
        subtitle_color = (57, 104, 126)    # #39687E
    else:
        raise ValueError(f"invalid user_status: {user_status!r}")

    # Step 2 — scale 与头部尺寸（以 320x70 为设计基准，按宽度等比缩放）
    W = img.width
    scale = W / 320
    head_h = round(70 * scale)

    # Step 3 — 头部底色：img 顶部 5 行像素的平均 RGB（只读，不改 img）
    rows = min(5, img.height)
    top = img.crop((0, 0, W, rows)).convert("RGB")
    avg = top.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    bg_color = (avg[0], avg[1], avg[2])

    # Step 4 — 建 head 画布
    head = Image.new("RGBA", (W, head_h), bg_color + (255,))

    # Step 5 — 药丸容器：半透明深色遮罩（必须经 overlay + alpha_composite 才能正确混合）
    pill_x = round(10 * scale)
    pill_y = round(7 * scale)
    pill_w = round(300 * scale)
    pill_h = round(56 * scale)
    pill_radius = pill_h // 2  # 真药丸：圆角半径 = 高度的一半

    pill_overlay = Image.new("RGBA", (W, head_h), (0, 0, 0, 0))
    ImageDraw.Draw(pill_overlay).rounded_rectangle(
        (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
        radius=pill_radius,
        fill=(0, 0, 0, 120),
    )
    head = Image.alpha_composite(head, pill_overlay)

    # Step 6 — 内矩形与内容坐标（内矩形 = 药丸去掉两端弧后的直段区域）
    inner_left = pill_x + pill_radius
    inner_right = pill_x + pill_w - pill_radius

    avatar_size = round(42 * scale)
    avatar_x = inner_left                       # 贴内矩形左缘
    avatar_y = pill_y + round(7 * scale)       # 内矩形上下各 7px 边距
    avatar_right = avatar_x + avatar_size

    text_x = avatar_right + round(10 * scale)   # 头像右侧间隔 10
    text_max_width = inner_right - text_x

    # Step 7 — 头像：下载/缓存 → 中心裁方 → 缩放 → 圆角方遮罩 → 粘贴
    m = _URL_HASH_PATTERN.search(user_avatar)
    if m:
        avatar_cache = CACHE_DIR / f"{m.group(0)}.jpg"
    else:
        avatar_cache = CACHE_DIR / f"{hashlib.md5(user_avatar.encode()).hexdigest()}.jpg"
    avatar = await _load_or_download(user_avatar, avatar_cache)

    side = min(avatar.width, avatar.height)
    left = (avatar.width - side) // 2
    top0 = (avatar.height - side) // 2
    avatar = avatar.crop((left, top0, left + side, top0 + side))
    avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

    avatar_radius = round(8 * scale)
    mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, avatar_size - 1, avatar_size - 1),
        radius=avatar_radius,
        fill=255,
    )
    avatar.putalpha(mask)
    head.paste(avatar, (avatar_x, avatar_y), avatar)

    # Step 8 — 文本：两行左对齐，超出内矩形右缘用 "…" 截断。
    # 自适应字号：从最大字高向下搜索，
    # 找到首个两行文本均能完整放下的字号；若到最小可读字高仍放不下，
    # 则用最小字号并截断。这样短名用大字，长名自动缩小
    # 以完整显示，避免过早被 "…" 截断。两行文本块在头像垂直跨度内居中。
    max_line_h = round(20 * scale)
    min_line_h = round(14 * scale)
    line_h = min_line_h
    font_line = _font_with_height(min_line_h)
    for lh in range(max_line_h, min_line_h - 1, -1):
        f = _font_with_height(lh)
        if (f.getlength(user_name) <= text_max_width
                and f.getlength(subtitle_text) <= text_max_width):
            line_h = lh
            font_line = f
            break
    username_disp = _truncate_to_width(user_name, font_line, text_max_width)
    subtitle_disp = _truncate_to_width(subtitle_text, font_line, text_max_width)

    text_block_h = line_h * 2
    text_top = avatar_y + (avatar_size - text_block_h) // 2
    username_y = text_top
    subtitle_y = text_top + line_h
    draw = ImageDraw.Draw(head)
    draw.text((text_x, username_y), username_disp, font=font_line, fill=username_color)
    draw.text((text_x, subtitle_y), subtitle_disp, font=font_line, fill=subtitle_color)

    # Step 9 — 合成返回（head 在上，img 在下；RGBA → RGB 白色背景，便于直接存 JPEG）
    img_rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    combined = Image.new("RGBA", (W, img.height + head_h), (0, 0, 0, 0))
    combined.alpha_composite(head, (0, 0))
    combined.alpha_composite(img_rgba, (0, head_h))
    # 转换为带白色背景的 RGB，避免业务代码保存 JPEG 报错
    if combined.mode == "RGBA":
        bg = Image.new("RGB", combined.size, (255, 255, 255))
        bg.paste(combined, mask=combined.split()[3])
        return bg
    elif combined.mode != "RGB":
        return combined.convert("RGB")
    else:
        return combined

# —— Steam 风格游戏成就列表配色 ——
_ACH_BG_B        = (0x1b, 0x28, 0x38)   # 顶部面板 B 底 #1b2838
_ACH_BG_C        = (0x2a, 0x47, 0x5e)   # 成就格 C 底 #2a475e
_ACH_SUBTITLE    = (0x66, 0xc0, 0xf4)   # "游戏成就列表" #66c0f4
_ACH_NAME        = (0xff, 0xff, 0xff)   # 成就名 #ffffff
_ACH_NAME_LOCKED = (0xb0, 0xb0, 0xb0)   # 未解锁成就名（灰白，区别于简介灰）#b0b0b0
_ACH_DESC        = (0x8f, 0x98, 0xa0)   # 成就简介 #8f98a0
_ACH_GAME_NAME   = (0xff, 0xff, 0xff)   # 游戏名 #ffffff
_ACH_PLACEHOLDER = (0x3a, 0x4f, 0x5e, 0xff)  # 图片下载失败占位色
_ACH_COLS        = 4                    # 网格列数


async def _safe_load_ach_icon(
    url: str, size: int, grayscale: bool = False
) -> Image.Image:
    """下载成就图，中心裁方后缩放到 size×size；空 url 或失败返回纯色占位。

    grayscale=True 时转灰度（保留 alpha），用于未解锁成就的黑白图标。
    """
    if not url:
        return Image.new("RGBA", (size, size), _ACH_PLACEHOLDER)
    m = _URL_HASH_PATTERN.search(url)
    h = m.group(0) if m else hashlib.md5(url.encode()).hexdigest()
    cache_path = CACHE_DIR / f"{h}.jpg"
    try:
        img = await _load_or_download(url, cache_path)
    except Exception:
        return Image.new("RGBA", (size, size), _ACH_PLACEHOLDER)
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    if grayscale:
        # 转灰度并保留原 alpha 通道（未解锁成就图标黑白化）
        alpha = img.getchannel("A") if img.mode == "RGBA" else None
        img = img.convert("L").convert("RGBA")
        if alpha is not None:
            img.putalpha(alpha)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _center_text_x(center_x: int, text: str, font: ImageFont.FreeTypeFont) -> int:
    """返回使 text 在 center_x 处水平居中的左上角 x 坐标。"""
    return center_x - int(font.getlength(text) // 2)


async def draw_archivement_info(
    game_name: str,
    unlocked_list: list[tuple[str, str, str]],
    locked_list: list[tuple[str, str, str]] | None = None,
) -> Image.Image:
    """绘制 Steam 风格游戏成就列表图片。

    unlocked_list / locked_list 元素均为 (成就图片url, 成就名称, 成就简介)。
    未解锁成就接在已解锁成就之后「另起一行」渲染（已解锁末行不满时右侧留白，
    未解锁从新的一行开始）；未解锁的图标黑白化、名称用灰白色。
    画布宽度固定 505*s，高度按总行数（4 列）自适应。
    """
    s = 1.0  # 整体等比缩放系数（可调；放大可减少文字截断）

    # 1) 整数像素尺寸（统一 round(*s) 防累计漂移）
    A_W = round(505 * s);  B_W = round(485 * s)
    B_x = (A_W - B_W) // 2
    B_radius = C_radius = round(10 * s)
    game_top = round(10 * s);  game_h = round(25 * s)
    sub_top = game_top + game_h + round(10 * s);  sub_h = round(20 * s)
    grid_top = round(80 * s);  cell = round(100 * s)
    col_gap = row_gap = round(15 * s)
    grid_left_pad = round(20 * s);  grid_bottom_pad = round(15 * s)
    icon_size = round(48 * s);  icon_top_pad = round(8 * s)
    name_h = round(14 * s);  desc_h = round(10 * s)  # 简介字号缩小，单行容纳更多
    text_gap = round(3 * s);  text_h_pad = round(4 * s)

    locked_list = locked_list or []
    n_unlocked = len(unlocked_list)
    n_locked = len(locked_list)
    R_unlocked = ceil(n_unlocked / _ACH_COLS) if n_unlocked else 0
    R_locked = ceil(n_locked / _ACH_COLS) if n_locked else 0
    R = R_unlocked + R_locked  # 未解锁「另起一行」，总行数 = 两段行数之和
    grid_h = R * cell + (R - 1) * row_gap if R else 0
    B_H = A_H = grid_top + grid_h + grid_bottom_pad  # B 贴画布顶部，A 高 = B 高

    # 2) 字体
    font_game = _font_with_height(game_h)
    font_sub = _font_with_height(sub_h)
    font_name = _font_with_height(name_h)
    font_desc = _font_with_height(desc_h)

    # 3) 并发下载成就图（未解锁图标由调用方传入 icongray URL，无需本地转灰度）
    icons_unlocked = (await asyncio.gather(
        *[_safe_load_ach_icon(t[0], icon_size, grayscale=False)
          for t in unlocked_list]
    )) if unlocked_list else []
    icons_locked = (await asyncio.gather(
        *[_safe_load_ach_icon(t[0], icon_size, grayscale=False)
          for t in locked_list]
    )) if locked_list else []

    # 4) 画布 A + 面板 B（不透明填充，直接画在 RGBA 画布上）
    canvas = Image.new("RGBA", (A_W, A_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (B_x, 0, B_x + B_W, B_H), radius=B_radius, fill=_ACH_BG_B + (255,)
    )

    B_center_x = B_x + B_W // 2
    game_max_w = B_W - 2 * round(20 * s)

    # 5) 游戏名（截断 + 居中）
    game_disp = _truncate_to_width(game_name, font_game, game_max_w)
    draw.text(
        (_center_text_x(B_center_x, game_disp, font_game), game_top),
        game_disp, font=font_game, fill=_ACH_GAME_NAME,
    )

    # 6) 副标题 "游戏成就列表"
    sub_text = "游戏成就列表"
    draw.text(
        (_center_text_x(B_center_x, sub_text, font_sub), sub_top),
        sub_text, font=font_sub, fill=_ACH_SUBTITLE,
    )

    # 7) 空列表短路（已解锁与未解锁均为空）
    if R == 0:
        empty = "暂无成就数据"
        f_e = _font_with_height(round(16 * s))
        draw.text(
            (_center_text_x(B_center_x, empty, f_e), grid_top + round(10 * s)),
            empty, font=f_e, fill=_ACH_DESC,
        )
        return canvas

    # 8) 成就格：已解锁段（row 0..R_unlocked-1）+ 未解锁段（row R_unlocked..R-1）
    text_max_w = cell - 2 * text_h_pad

    def _render_cell(
        idx_in_segment: int, row_offset: int, icon: Image.Image,
        name: str, desc: str, name_color: tuple,
    ) -> None:
        col = idx_in_segment % _ACH_COLS
        row = row_offset + idx_in_segment // _ACH_COLS
        cx = B_x + grid_left_pad + col * (cell + col_gap)
        cy = grid_top + row * (cell + row_gap)

        # 容器 C
        draw.rounded_rectangle(
            (cx, cy, cx + cell, cy + cell), radius=C_radius, fill=_ACH_BG_C + (255,)
        )

        # 成就图（水平居中，距 C 顶 8*s）
        ix = cx + (cell - icon_size) // 2
        iy = cy + icon_top_pad
        canvas.paste(icon, (ix, iy), icon)

        # 文本区：在"图下方剩余区域"内垂直居中
        icon_bottom = iy + icon_size
        region_h = (cy + cell) - icon_bottom
        block_h = name_h + text_gap + desc_h
        name_top = icon_bottom + (region_h - block_h) // 2
        desc_top = name_top + name_h + text_gap
        ccx = cx + cell // 2  # 格子水平中心

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