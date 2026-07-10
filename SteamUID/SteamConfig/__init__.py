from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsStrConfig,
    GsIntConfig,
    GsBoolConfig,
    GsListStrConfig
)
from gsuid_core.utils.plugins_config.gs_config import StringConfig
from gsuid_core.data_store import get_res_path

CONFIG_PATH = get_res_path() / 'SteamUID'

CONFIG_DEFAULT: dict[str, GSC] = {
    "SteamWebAPIKey": GsStrConfig(
        "Steam Web API Key",
        "前往 https://steamcommunity.com/dev/apikey 申请",
        "",
        secret=True,
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
        "用户状态轮询间隔",
        "用户状态轮询间隔，单位秒。修改后需重启 GsCore 生效",
        20,
    ),
    "ArchivementsPollInterval": GsIntConfig(
        "成就轮询间隔",
        "成就轮询间隔，单位秒。修改后需重启 GsCore 生效",
        60,
    ),
    "OnlyOpenID": GsBoolConfig(
        "仅允许网页登录",
        "开启后将不支持用户手动传入steamid，而采用 Openid 验证 steamid 所有权后绑定",
        False,
    ),
    "PushSwitch": GsListStrConfig(
        "推送总开关",
        "选择开启的推送事件，关闭的事件将不会推送(无论用户设置是否开启)",
        ["开始游戏","结束游戏","获得成就"],
        options=[
            "开始游戏",
            "结束游戏",
            "获得成就",
        ]
    ),
    "PushDefault": GsListStrConfig(
        "默认开启推送事件",
        "用户绑定steam账号后对应steam账号默认开启的推送事件",
        ["开始游戏","结束游戏","获得成就"],
        options=[
            "开始游戏",
            "结束游戏",
            "获得成就",
        ]
    ),
    "pricecc": GsStrConfig(
        "steam地区代码",
        "监听游戏降价的steam地区，默认中国大陆。其他国家代码请参照 ISO 3166-1 alpha-2",
        "cn"
    ),
    "GameSaleInterval": GsIntConfig(
        "游戏降价轮询间隔",
        "游戏降价轮询间隔，单位小时。修改后需重启 GsCore 生效",
        6,
    ),

}
CONFIG_PATH.mkdir(parents=True, exist_ok=True)
SteamConfig = StringConfig("SteamConfig",CONFIG_PATH / 'config.json',CONFIG_DEFAULT)