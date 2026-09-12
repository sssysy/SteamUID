from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsStrConfig,
    GsIntConfig,
    GsBoolConfig,
    GsListStrConfig,
    GsTimeRConfig,
)
from gsuid_core.utils.plugins_config.gs_config import StringConfig
from gsuid_core.data_store import get_res_path

from .region_map import (
    SUPPORTED_REGIONS,
    SteamRegion,
    get_region,
    get_current_region,
    get_current_cc,
    get_current_lang,
    get_current_currency,
)

CONFIG_PATH = get_res_path() / 'SteamUID'

CONFIG_DEFAULT: dict[str, GSC] = {
    "SteamWebAPIKey": GsStrConfig(
        "Steam Web API Key",
        "前往 https://steamcommunity.com/dev/apikey 申请",
        "",
        secret=True,
    ),
    "APIBaseURL": GsStrConfig(
        "SteamAPI反代URL",
        "steamAPI基础URL，用于反代",
        "https://api.steampowered.com",
    ),
    "storeBaseURL": GsStrConfig(
        "Steam商店反代URL",
        "steam商店基础URL，用于反代",
        "https://store.steampowered.com",
    ),
    "CommunityBaseURL": GsStrConfig(
        "Steam社区反代URL",
        "steam社区基础URL，用于miniprofile等社区接口",
        "https://steamcommunity.com",
    ),
    "PollInterval": GsIntConfig(
        "用户状态轮询间隔 (秒)",
        "用户状态轮询间隔。修改后需重启 GsCore 生效",
        20,
    ),
    "ArchivementsPollInterval": GsIntConfig(
        "成就轮询间隔 (秒)",
        "成就轮询间隔。修改后需重启 GsCore 生效",
        60,
    ),
    "CacheTime": GsIntConfig(
        "数据接口缓存过期时间 (天)",
        "缓存json(游戏成就信息 / 游戏详情信息等)过期时间。修改后需重启 GsCore 生效",
        3,
    ),
    "FileCacheTime": GsIntConfig(
        "缓存文件过期时间 (天)",
        "缓存文件过期时间，超过此天数的文件会删除，0不启用。修改后需重启 GsCore 生效",
        0,
    ),
    "GameSaleInterval": GsIntConfig(
        "游戏降价轮询间隔 (小时)",
        "游戏降价轮询间隔。修改后需重启 GsCore 生效",
        6,
    ),
    "GameAnnounceInterval": GsIntConfig(
        "游戏公告轮询间隔 (小时)",
        "游戏公告轮询间隔。修改后需重启 GsCore 生效",
        1,
    ),
    "gscoreBaseURL": GsStrConfig(
        "steamOpenid登录基础URL",
        "应为 gscore 的公网地址或穿透地址",
        "http://127.0.0.1:8765",
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
    "StatusChangeCD": GsIntConfig(
        "状态变更冷却CD (分钟)",
        "状态变更推送群聊冷却时间 (分钟)，设置为0则不启用",
        5,
    ),
    "country": GsStrConfig(
        "steam地区",
        "监听游戏降价及获取商店数据的 steam 地区，默认中国大陆",
        "中国大陆",
        options=SUPPORTED_REGIONS,
    ),
    "AllowAt": GsBoolConfig(
        "允许 @ 他人获取他人信息",
        "开启后将支持用户通过 '@用户 + steam xxx' 功能获取对方信息",
        False,
    ),
    "HideSteamID": GsBoolConfig(
        "隐藏 steamid / 好友码",
        "开启后将会在可能出现 steamid / 好友码的地方隐藏相关数字的中间部分",
        False,
    ),
    "AllowPrivateDataWithAuth": GsBoolConfig(
        "登录后允许展示私密数据",
        "比如用户设置游戏库存为隐私后，通过web api key无法获取，开启且用户登录后将使用用户凭证获取",
        True,
    ),
    "HttpProxy": GsStrConfig(
        "Steam HTTP代理URL",
        "用于 Steam 登录及 Web 请求的代理（如 http://127.0.0.1:7890，留空则直连）",
        "",
    ),
    "AutoQueueCount": GsIntConfig(
        "每次探索队列次数",
        "每次执行探索队列时的轮数，默认为 3 次",
        3,
    ),
    "AutoQueueInterval": GsIntConfig(
        "探索队列间隔",
        "探索队列每轮之间的等待间隔（秒），默认为 15 秒",
        15,
    ),
    "AutoQueueTime": GsTimeRConfig(
        "自动探索队列时间",
        "每日自动执行探索队列的时间 (时, 分)。修改后需重启 GsCore 生效",
        (8, 0),
    ),
    "QueuePushPrivate": GsBoolConfig(
        "探索队列结果私聊推送",
        "自动探索队列执行完毕后是否通过私聊向开启用户推送结果",
        False,
    ),
    "QueuePushGroup": GsBoolConfig(
        "探索队列结果群聊推送",
        "自动探索队列执行完毕后是否向开启所在的群聊推送结果",
        True,
    ),
}

CONFIG_PATH.mkdir(parents=True, exist_ok=True)
SteamConfig = StringConfig("SteamConfig",CONFIG_PATH / 'config.json',CONFIG_DEFAULT)