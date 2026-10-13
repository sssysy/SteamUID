"""SteamUID 配置派生读取：回调基址 / 反代基址 / 地区 / 封面 Key / 推送选项 / 背景 / id 隐藏。"""

from pathlib import Path

from ..maps import (
    DEFAULT_REGION,
    SteamRegion,
    find_region,
)
from .status import PushOptions
from ..utils.mask import mask_id
from ...steam_config import DATA_DIR, SteamConfig
from ..api.endpoints import (
    API_BASE_DEFAULT,
    STORE_BASE_DEFAULT,
    COMMUNITY_BASE_DEFAULT,
)


def base_url() -> str:
    """OpenID 回调基址，去掉结尾斜杠。"""
    return SteamConfig.get_config("GsCoreBaseURL").data.strip().rstrip("/")


def _base_or_default(raw: str, default: str) -> str:
    """反代基址去空白；未配置时回落官方默认域名。"""
    return raw.strip() or default


def api_base() -> str:
    """Steam Web API 基础 URL，供反向代理替换。"""
    return _base_or_default(SteamConfig.get_config("APIBaseURL").data, API_BASE_DEFAULT)


def store_base() -> str:
    """Steam 商店基础 URL，供反向代理替换。"""
    return _base_or_default(SteamConfig.get_config("StoreBaseURL").data, STORE_BASE_DEFAULT)


def community_base() -> str:
    """Steam 社区基础 URL，供反向代理替换。"""
    return _base_or_default(SteamConfig.get_config("CommunityBaseURL").data, COMMUNITY_BASE_DEFAULT)


def hide_id(text: str) -> str:
    """按配置隐藏 steamid / 好友码中间数字；昵称等非纯数字文本原样返回。"""
    if not SteamConfig.get_config("HideSteamID").data or not text.isdigit():
        return text
    return mask_id(text)


def region() -> SteamRegion:
    """配置的 Steam 地区；取值未收录时回落默认地区。"""
    return find_region(SteamConfig.get_config("Region").data) or DEFAULT_REGION


def region_cc() -> str:
    """配置地区对应的 ISO 代码（大写），供商店相关接口的 cc 参数使用。"""
    return region().cc.upper()


def griddb_cover_key() -> str:
    """社区封面用 SteamGridDB API Key；总开关关闭或未配置时返回空串。"""
    if not SteamConfig.get_config("AllowGridDBCover").data:
        return ""
    return SteamConfig.get_config("GridDBApiKey").data.strip()


def push_options() -> PushOptions:
    """汇总一次推送所需的全部配置项。"""
    return PushOptions(
        kinds=frozenset(SteamConfig.get_config("NotifyTypes").data),
        cd_seconds=SteamConfig.get_config("NotifyCD").data * 60,
        mode=SteamConfig.get_config("PushMode").data,
        with_cover=SteamConfig.get_config("PushImage").data,
        region_cc=region_cc(),
        griddb_key=griddb_cover_key(),
    )


def custom_bg_path() -> Path | None:
    """配置声明的自定义背景文件；未上传、非上传目标文件或文件缺失时返回 None。"""
    config = SteamConfig.get_config("CustomBgPath")
    raw = config.data.strip()
    if not raw:
        return None
    path = Path(raw)
    # 只认控制台上传的目标文件，避免把数据目录里的其它文件放出去
    if path.parent != DATA_DIR or path.name != f"{config.filename}.{config.suffix}":
        return None
    if not path.is_file() or path.stat().st_size == 0:
        return None
    return path


def use_profile_card_bg() -> bool:
    """卡片底图是否优先使用账号个人资料背景。"""
    return bool(SteamConfig.get_config("CardUseProfileBg").data)
