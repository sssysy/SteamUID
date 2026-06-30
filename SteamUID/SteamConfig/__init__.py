from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsStrConfig,
    GsIntConfig,
)
from gsuid_core.utils.plugins_config.gs_config import StringConfig
from gsuid_core.data_store import get_res_path

CONFIG_PATH = get_res_path() / 'SteamUID'

CONFIG_DEFAULT: dict[str, GSC] = {
    "SteamWebAPIKey": GsStrConfig(
        "Steam Web API Key",
        "前往 https://steamcommunity.com/dev/apikey 申请",
        "",
    ),
    "APIBaseURL": GsStrConfig(
        "SteamAPIBaseURL",
        "steamAPI基础URL，用于反代",
        "https://api.steampowered.com",
    ),
    "storeBaseURL": GsStrConfig(
        "Steam商店BaseURL",
        "steam商店基础URL，用于反代",
        "https://store.steampowered.com",
    ),
    "gscoreBaseURL": GsStrConfig(
        "steam登录基础URL",
        "应为 gscore 的公网地址或穿透地址",
        "http://127.0.0.1:8765",
    ),
    "PollInterval": GsIntConfig(
        "轮询间隔",
        "轮询间隔，单位秒。修改后需重启 GsCore 生效",
        20,
    ),

}
CONFIG_PATH.mkdir(parents=True, exist_ok=True)
SteamConfig = StringConfig("SteamConfig",CONFIG_PATH / 'config.json',CONFIG_DEFAULT)