import math
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

# 方形分块网格：UNIT 2:3 与图源 library_600x900 同比例 → 等比缩放即不裁切不变形
UNIT_W = 48
UNIT_H = 72          # UNIT_W:UNIT_H = 2:3，与 library_600x900(600x900) 同比例
MAX_COLS = 40        # 列数上限：画布最大宽 = MAX_COLS * UNIT_W = 40 * 48 = 1920px
GAP = 0              # 无空隙
BG_COLOR = (0x1B, 0x28, 0x38)


def assign_N(playtime, max_playtime):
    """按时长相对最大值映射方形单元格边长 N∈{1..5}。
    N = clamp(round(1 + 4*sqrt(playtime/max_playtime)), 1, 5)
    面积 = N^2 ∝ 时长，最大游戏 N=5（面积约 25 倍）。
    """
    if max_playtime <= 0:
        return 1  # 防御：正常流程过滤后 max>=10，不会触发
    ratio = playtime / max_playtime
    n = round(1 + 4 * math.sqrt(ratio))
    return max(1, min(5, n))


def prepare_items(items):
    """
    items: [(path, playtime_minutes), ...]  path 可能为 None(下载失败)
    返回: [{"path","playtime","n"}, ...] 已过滤 None、过滤 <10 分钟、按时长降序、分配 N。
    """
    # 1 过滤 None 路径(下载失败，避免占用网格) + <10 分钟
    valid = [(p, t) for p, t in items if p is not None and t >= 10]
    if not valid:
        return []
    # 2 按时长降序
    valid.sort(key=lambda x: x[1], reverse=True)
    # 3 max_playtime 取过滤后最大值(降序后即首项)，避免被过滤项污染基准
    max_playtime = valid[0][1]
    # 4 分配 N
    out = []
    for path, playtime in valid:
        n = assign_N(playtime, max_playtime)
        out.append({"path": path, "playtime": playtime, "n": n})
    return out


def load_images(items, max_workers=8):
    """加载本地图片"""
    covers = {}

    def load(it):
        try:
            img = Image.open(it["path"]).convert("RGB")
            return it["path"], img
        except Exception:
            return it["path"], None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for path, img in ex.map(load, items):
            if img is not None:
                covers[path] = img
    return covers


class DenseGrid:
    """CSS Grid dense 布局：每个 item 从左上角 (0,0) 重新扫描首个可放位置。"""

    def __init__(self, cols):
        self.cols = max(1, cols)
        self.occupied = set()
        self.rows = 0
        self.placements = []  # [(item, r, c, w, h)]

    def _can_place(self, r, c, w, h):
        if c + w > self.cols:
            return False
        for rr in range(r, r + h):
            for cc in range(c, c + w):
                if (rr, cc) in self.occupied:
                    return False
        return True

    def place(self, item, w, h):
        """把 item(w×h) 放到首个可放位置；w 超过列数时降级避免死循环。"""
        if w > self.cols:
            w = self.cols
        r = 0
        while True:
            for c in range(self.cols):  # 行内从左到右
                if self._can_place(r, c, w, h):
                    for rr in range(r, r + h):
                        for cc in range(c, c + w):
                            self.occupied.add((rr, cc))
                    self.rows = max(self.rows, r + h)
                    self.placements.append((item, r, c, w, h))
                    return
            r += 1  # 行向下扩张


def fit_resize(img, tw, th):
    """等比缩放使图片完整放入 (tw, th) 内，不裁切不变形；不足部分留 BG_COLOR。
    图源为 2:3 时两方向 scale 相等，输出恰为目标尺寸，满填无空隙。
    """
    sw, sh = img.size
    scale = min(tw / sw, th / sh)
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    return img.resize((nw, nh), Image.LANCZOS)


def compute_cols(prepared):
    """根据内容动态计算列数，保证合成后为竖图(H>W)，列数尽可能大但不超过 MAX_COLS。

    依据：任何放置方式所需行数 rows >= ceil(A/列数)（A=所有游戏占用格子数之和）。
    若 ceil(A/列数)*UNIT_H > 列数*UNIT_W，则实际高度必 > 宽度 → 竖图必然成立。
    列数取满足该条件的最大值(上限 MAX_COLS)，使画布尽量宽；内容少时自动收窄以保证竖图。
    """
    A = sum(it["n"] ** 2 for it in prepared)
    if A <= 0:
        return 1
    best = 1
    for cols in range(1, MAX_COLS + 1):
        min_rows = (A + cols - 1) // cols  # ceil(A / cols)
        if min_rows * UNIT_H > cols * UNIT_W:  # 等价 min_rows*3 > cols*2
            best = cols  # 条件随 cols 单调由真转假，best 即最大满足者
    return best


def compose(grid, covers, cols):
    """把所有格子合成到画布，返回 PIL.Image。宽 = cols*UNIT_W，高随行数自适应。"""
    W = cols * UNIT_W
    H = grid.rows * UNIT_H if grid.rows > 0 else UNIT_H
    canvas = Image.new("RGB", (W, H), BG_COLOR)

    for item, r, c, w, h in grid.placements:
        cover = covers.get(item["path"])
        tw, th = w * UNIT_W, h * UNIT_H                 # w==h==N，GAP=0
        x, y = c * UNIT_W, r * UNIT_H
        if cover is not None:
            tile = fit_resize(cover, tw, th)
            # 居中 paste：2:3 图源恰好填满；非 2:3 两侧/上下留 BG_COLOR
            px = x + (tw - tile.width) // 2
            py = y + (th - tile.height) // 2
            canvas.paste(tile, (px, py))

    return canvas


def build_wall(items):
    """
    根据本地图片 + 游戏时长生成封面墙，返回 PIL.Image。

    参数:
        items: [(图片路径(str|None), 游戏时长(int, 分钟)), ...]
               None 路径与 <10 分钟项会被过滤。

    返回:
        PIL.Image.Image —— 宽 ≤1920px(动态列数保证竖图 H>W)、高自适应的封面墙

    异常:
        ValueError —— 列表为空、路径全为 None 或全部被 <10 分钟过滤时抛出
    """
    prepared = prepare_items(items)
    if not prepared:
        raise ValueError("没有可用的图片（列表为空、路径为 None 或全部被 <10 分钟过滤）")

    covers = load_images(prepared)

    cols = compute_cols(prepared)          # 动态列数：保证竖图(H>W)，上限 MAX_COLS
    grid = DenseGrid(cols)
    for it in prepared:
        grid.place(it, it["n"], it["n"])   # N×N 方形区域(恒 2:3)

    return compose(grid, covers, cols)
