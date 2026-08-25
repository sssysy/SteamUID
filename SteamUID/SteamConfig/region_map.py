from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SteamRegion:
    """Steam 地区与多语言数据结构"""
    name: str       # 中文名称（用于前端下拉选项与展示）
    cc: str         # ISO 3166-1 alpha-2 地区代码（用于价格与地区接口，如 cn, hk, us）
    lang: str       # Steam API 官方语言代码（用于 l/language 参数，如 schinese, tchinese, english）
    currency: str   # 货币符号（用于价格展示，如 ¥, HK$, NT$, $）


# Steam 官方支持的主要独立商店定价与多语言国家/地区列表（排除无独立定价或未开通 Steam 服务的国家）
_STEAM_REGIONS_LIST: list[SteamRegion] = [
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
]

# 默认回退地区
DEFAULT_REGION = _STEAM_REGIONS_LIST[0]  # 中国大陆 (cn / schinese)

# 提供给配置项 options 的地区名称列表
SUPPORTED_REGIONS: list[str] = [r.name for r in _STEAM_REGIONS_LIST]

# 别名/代码快速索引表
_ALIAS_MAP: dict[str, SteamRegion] = {}
for r in _STEAM_REGIONS_LIST:
    _ALIAS_MAP[r.name.lower()] = r
    _ALIAS_MAP[r.cc.lower()] = r
    # 部分常用别名
    if r.cc == "cn":
        _ALIAS_MAP["中国"] = r
        _ALIAS_MAP["国内"] = r
        _ALIAS_MAP["大陆"] = r
        _ALIAS_MAP["schinese"] = r
    elif r.cc == "hk":
        _ALIAS_MAP["香港"] = r
        _ALIAS_MAP["hongkong"] = r
    elif r.cc == "tw":
        _ALIAS_MAP["台湾"] = r
        _ALIAS_MAP["taiwan"] = r
    elif r.cc == "gb":
        _ALIAS_MAP["uk"] = r
        _ALIAS_MAP["英国"] = r
    elif r.cc == "us":
        _ALIAS_MAP["usa"] = r
        _ALIAS_MAP["america"] = r
    elif r.cc == "jp":
        _ALIAS_MAP["japan"] = r


def get_region(query: Optional[str]) -> SteamRegion:
    """根据地区名称、ISO 国家代码或别名解析对应的 SteamRegion 对象。

    若未找到或传入为空，默认回退至 DEFAULT_REGION（中国大陆）。
    """
    if not query:
        return DEFAULT_REGION

    q = str(query).strip().lower()
    return _ALIAS_MAP.get(q, DEFAULT_REGION)


def get_current_region() -> SteamRegion:
    """从 SteamConfig 中读取当前配置的地区并解析为 SteamRegion。"""
    try:
        from . import SteamConfig
        # 优先读取新配置 country，兼容老配置 pricecc
        country_cfg = None
        try:
            country_cfg = SteamConfig.get_config("country").data
        except Exception:
            pass

        if not country_cfg:
            try:
                country_cfg = SteamConfig.get_config("pricecc").data
            except Exception:
                pass

        if isinstance(country_cfg, list) and country_cfg:
            country_cfg = country_cfg[0]

        return get_region(country_cfg)
    except Exception:
        return DEFAULT_REGION


def get_current_cc() -> str:
    """获取当前配置的 Steam 地区代码（如 cn, hk, us, jp 等）。"""
    return get_current_region().cc


def get_current_lang() -> str:
    """获取当前配置的 Steam 官方 API 语言代号（如 schinese, tchinese, english, japanese 等）。"""
    return get_current_region().lang


def get_current_currency() -> str:
    """获取当前配置的 Steam 地区货币符号（如 ¥, HK$, NT$, $ 等）。"""
    return get_current_region().currency
