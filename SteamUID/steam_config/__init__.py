"""SteamUID 插件配置项定义与注册。"""

from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.models import GSC, GsStrConfig, GsBoolConfig
from gsuid_core.utils.plugins_config.gs_config import StringConfig

CONFIG_PATH = get_res_path("SteamUID") / "config.json"

CONFIG_DEFAULT: dict[str, GSC] = {
    "GsCoreBaseURL": GsStrConfig(
        "GsCore 公网地址",
        "Steam OpenID 回调基址，需为外网可访问的 gsuid_core 地址（含协议）",
        "http://127.0.0.1:8765",
    ),
    "AllowAt": GsBoolConfig(
        "允许 @ 他人",
        "开启后可通过 @ 指定他人进行绑定 / 解绑 / 查看",
        False,
    ),
}

SteamConfig = StringConfig("SteamUID", CONFIG_PATH, CONFIG_DEFAULT)


def get_base_url() -> str:
    """OpenID 回调基址，去掉结尾斜杠。"""
    config = SteamConfig.get_config("GsCoreBaseURL")
    if not isinstance(config, GsStrConfig):
        logger.error("[Steam·账户绑定] 配置项 GsCoreBaseURL 类型异常")
        return ""
    return config.data.strip().rstrip("/")


def get_allow_at() -> bool:
    """是否允许 @ 他人。"""
    config = SteamConfig.get_config("AllowAt")
    if not isinstance(config, GsBoolConfig):
        logger.error("[Steam·账户绑定] 配置项 AllowAt 类型异常")
        return False
    return config.data
