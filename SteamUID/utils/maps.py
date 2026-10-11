"""Steam 静态映射表与纯解析：等级徽章样式、商店地区与地区旗帜。

只放不依赖网络与数据库的表与纯函数；取图落盘由 helper 层负责。
"""

from dataclasses import dataclass

# 等级十位段位 -> 圆环主色，用于 100 级以下的圆形徽章
LEVEL_BORDER_COLORS: dict[int, str] = {
    0: "#9b9b9b",
    10: "#c02942",
    20: "#d95b43",
    30: "#fecc23",
    40: "#467a3c",
    50: "#4e8ddb",
    60: "#7652c9",
    70: "#c252c9",
    80: "#542437",
    90: "#997c52",
}

# 等级百位段位 -> 官方图案文件名，取自 Steam 社区等级徽章精灵图
LEVEL_PATTERN_FILES: dict[int, str] = {
    100: "levels_hexagons.png",
    200: "levels_shields.png",
    300: "levels_books.png",
    400: "levels_chevrons.png",
    500: "levels_circle2.png",
    600: "levels_angle.png",
    700: "levels_flag.png",
    800: "levels_wings.png",
    900: "levels_arrows.png",
    1000: "levels_crystals.png",
    1100: "levels_space.png",
    1200: "levels_waterelement.png",
    1300: "levels_fireelement.png",
    1400: "levels_earthelement.png",
    1500: "levels_airelement_1-2.png",
    1600: "levels_airelement_3-4.png",
    1700: "levels_airelement_5-6.png",
    1800: "levels_airelement_7-8.png",
    1900: "levels_airelement_9-10.png",
    2000: "levels_geo_1-2.png",
    2100: "levels_geo_3-4.png",
    2200: "levels_geo_5-6.png",
    2300: "levels_geo_7-8.png",
    2400: "levels_geo_9-10.png",
    2500: "levels_mandala_1-2.png",
    2600: "levels_mandala_3-4.png",
    2700: "levels_mandala_5-6.png",
    2800: "levels_mandala_7-8.png",
    2900: "levels_mandala_9-10.png",
    3000: "levels_spiro_1-2.png",
    3100: "levels_spiro_3-4.png",
    3200: "levels_spiro_5-6.png",
    3300: "levels_spiro_7-8.png",
    3400: "levels_spiro_9-10.png",
    3500: "levels_patterns_1-2.png",
    3600: "levels_patterns_3-4.png",
    3700: "levels_patterns_5-6.png",
    3800: "levels_patterns_7-8.png",
    3900: "levels_patterns_9-10.png",
    4000: "levels_shapes_1.png",
    4100: "levels_shapes_2.png",
    4200: "levels_shapes_3.png",
    4300: "levels_shapes_4.png",
    4400: "levels_shapes_5.png",
    4500: "levels_grunge_1.png",
    4600: "levels_grunge_2.png",
    4700: "levels_grunge_3.png",
    4800: "levels_grunge_4.png",
    4900: "levels_grunge_5.png",
    5000: "levels_halftone_1.png",
    5100: "levels_halftone_2.png",
    5200: "levels_halftone_3.png",
    5300: "levels_5300_dashes.png",
    5400: "levels_5400_crosshatch.png",
    5500: "levels_5500_spiral.png",
    5600: "levels_5600_leaves.png",
    5700: "levels_5700_mountain.png",
    5800: "levels_5800_rain.png",
    5900: "levels_5900_tornado.png",
    6000: "levels_6000_snowflake.png",
    6100: "levels_6100_crown.png",
}

# 官方精灵图为 10 帧纵排，每帧 32px，帧序即十位段位
LEVEL_FRAME_STEP_PX = 32
LEVEL_FRAME_COUNT = 10
_LEVEL_PATTERN_MIN = 100


@dataclass(frozen=True)
class LevelStyle:
    """等级徽章样式：圆环色 + 官方图案文件名与帧偏移（无图案时为空）。"""

    border_color: str
    sprite_file: str
    offset_px: int


def level_style(level: int) -> LevelStyle:
    """按等级推导徽章样式；100 级以上用官方图案，帧序取十位段位。"""
    decade = level // 10 * 10
    border_color = LEVEL_BORDER_COLORS.get(decade, "#9b9b9b")
    if level < _LEVEL_PATTERN_MIN:
        return LevelStyle(border_color=border_color, sprite_file="", offset_px=0)

    hundred = level // 100 * 100
    sprite_file = LEVEL_PATTERN_FILES.get(hundred, "")
    if not sprite_file:
        return LevelStyle(border_color=border_color, sprite_file="", offset_px=0)

    frame = level % 100 // 10 % LEVEL_FRAME_COUNT
    return LevelStyle(
        border_color=border_color,
        sprite_file=sprite_file,
        offset_px=-frame * LEVEL_FRAME_STEP_PX,
    )


_REGIONAL_OFFSET = 0x1F1E6 - ord("A")


def flag_emoji(country_code: str) -> str:
    """ISO 3166-1 alpha-2 转旗帜 emoji；非两位字母返回空串。"""
    code = country_code.strip().upper()
    if len(code) != 2 or not code.isalpha() or not code.isascii():
        return ""
    return "".join(chr(ord(ch) + _REGIONAL_OFFSET) for ch in code)


@dataclass(frozen=True)
class SteamRegion:
    """Steam 商店地区：展示名、ISO 代码、接口语言代码与货币符号。"""

    name: str
    cc: str
    lang: str
    currency: str


# 有独立定价的 Steam 地区，清单取旧版 main 的 SteamConfig/region_map（去掉了别名表）
STEAM_REGIONS: tuple[SteamRegion, ...] = (
    SteamRegion("中国大陆", "cn", "schinese", "¥"),
    SteamRegion("中国香港", "hk", "tchinese", "HK$"),
    SteamRegion("中国台湾", "tw", "tchinese", "NT$"),
    SteamRegion("日本", "jp", "japanese", "¥"),
    SteamRegion("韩国", "kr", "koreana", "₩"),
    SteamRegion("美国", "us", "english", "$"),
    SteamRegion("英国", "gb", "english", "£"),
    SteamRegion("加拿大", "ca", "english", "C$"),
    SteamRegion("澳大利亚", "au", "english", "A$"),
    SteamRegion("俄罗斯", "ru", "russian", "₽"),
    SteamRegion("德国", "de", "german", "€"),
    SteamRegion("法国", "fr", "french", "€"),
    SteamRegion("西班牙", "es", "spanish", "€"),
    SteamRegion("意大利", "it", "italian", "€"),
    SteamRegion("荷兰", "nl", "dutch", "€"),
    SteamRegion("波兰", "pl", "polish", "zł"),
    SteamRegion("乌克兰", "ua", "ukrainian", "₴"),
    SteamRegion("巴西", "br", "brazilian", "R$"),
    SteamRegion("阿根廷", "ar", "latam", "$"),
    SteamRegion("土耳其", "tr", "turkish", "$"),
    SteamRegion("新加坡", "sg", "english", "S$"),
    SteamRegion("马来西亚", "my", "english", "RM"),
    SteamRegion("泰国", "th", "thai", "฿"),
    SteamRegion("越南", "vn", "vietnamese", "₫"),
    SteamRegion("印度尼西亚", "id", "indonesian", "Rp"),
    SteamRegion("菲律宾", "ph", "english", "₱"),
    SteamRegion("印度", "in", "english", "₹"),
    SteamRegion("墨西哥", "mx", "latam", "Mex$"),
    SteamRegion("智利", "cl", "latam", "CLP$"),
    SteamRegion("哥伦比亚", "co", "latam", "COL$"),
    SteamRegion("秘鲁", "pe", "latam", "S/."),
    SteamRegion("沙特阿拉伯", "sa", "arabic", "SR"),
    SteamRegion("阿联酋", "ae", "arabic", "AED"),
    SteamRegion("南非", "za", "english", "R"),
    SteamRegion("瑞士", "ch", "german", "CHF"),
    SteamRegion("瑞典", "se", "swedish", "kr"),
    SteamRegion("挪威", "no", "norwegian", "kr"),
    SteamRegion("丹麦", "dk", "danish", "kr."),
    SteamRegion("芬兰", "fi", "finnish", "€"),
    SteamRegion("捷克", "cz", "czech", "Kč"),
    SteamRegion("匈牙利", "hu", "hungarian", "Ft"),
    SteamRegion("罗马尼亚", "ro", "romanian", "lei"),
    SteamRegion("保加利亚", "bg", "bulgarian", "лв"),
    SteamRegion("希腊", "gr", "greek", "€"),
    SteamRegion("新西兰", "nz", "english", "NZ$"),
)

DEFAULT_REGION: SteamRegion = STEAM_REGIONS[0]
SUPPORTED_REGIONS: list[str] = [region.name for region in STEAM_REGIONS]

_REGION_INDEX: dict[str, SteamRegion] = {}
for _region in STEAM_REGIONS:
    _REGION_INDEX[_region.name] = _region
    _REGION_INDEX[_region.cc] = _region


def find_region(query: str) -> SteamRegion | None:
    """按地区名或 ISO 代码精确查找；未收录返回 None 交由调用方决策。"""
    key = query.strip().lower()
    if key in _REGION_INDEX:
        return _REGION_INDEX[key]
    return None
