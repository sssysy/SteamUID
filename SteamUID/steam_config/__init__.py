"""SteamUID 插件配置项定义与注册。"""

from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsDivider,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsImageConfig,
    GsTimeRConfig,
    GsListStrConfig,
)
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from ..utils.maps import (
    DEFAULT_REGION,
    SUPPORTED_REGIONS,
)
from ..utils.api.endpoints import (
    API_BASE_DEFAULT,
    STORE_BASE_DEFAULT,
    COMMUNITY_BASE_DEFAULT,
)
from ..utils.helper.status import (
    PUSH_MODES,
    NOTIFY_KINDS,
    DEFAULT_PUSH_MODE,
)

DATA_DIR = get_res_path("SteamUID")
CONFIG_PATH = DATA_DIR / "config.json"

CONFIG_DEFAULT: dict[str, GSC] = {
    "_NetworkDivider": GsDivider(
        "网络请求和代理配置",
        "",
    ),
    "GsCoreBaseURL": GsStrConfig(
        "GsCore 公网地址",
        "Steam OpenID 回调 BaseURL，需为外网可访问的 gsuid_core 地址",
        "http://127.0.0.1:8765",
    ),
    "APIBaseURL": GsStrConfig(
        "Steam API 反代 URL",
        "Steam Web API 基础 URL",
        API_BASE_DEFAULT,
    ),
    "StoreBaseURL": GsStrConfig(
        "Steam 商店反代 URL",
        "Steam 商店基础 URL",
        STORE_BASE_DEFAULT,
    ),
    "CommunityBaseURL": GsStrConfig(
        "Steam 社区反代 URL",
        "Steam 社区基础 URL，用于迷你资料等社区接口",
        COMMUNITY_BASE_DEFAULT,
    ),
    "Region": GsStrConfig(
        "steam 地区",
        "价格 / 商店搜索 / 封面等接口传递的地区，同时决定价格展示的货币符号",
        DEFAULT_REGION.name,
        options=SUPPORTED_REGIONS,
    ),
    "SteamAPIKey": GsListStrConfig(
        "Steam API Key",
        "前往 [Steam社区](https://steamcommunity.com/dev/apikey) 申请；可配置多个 Key 轮换",
        [],
        secret=True,
    ),
    "KeyPoolCooldown": GsIntConfig(
        "API Key 请求过多冷却 (秒)",
        "单个 Key 触发请求过多后的冷却秒数",
        600,
    ),
    "KeyRetryCount": GsIntConfig(
        "API Key 重试次数",
        "轮询任务出错时额外重试次数，0 表示不重试",
        5,
    ),
    "NotifyKeyExhausted": GsBoolConfig(
        "Key 全失效时私信主人",
        "开启后，所有 Steam API Key 判定失效时私信主人",
        True,
    ),
    "AllowGridDBCover": GsBoolConfig(
        "允许备选 Grid DB 封面",
        "官方封面均失败时改用 SteamGridDB 社区封面兜底",
        False,
    ),
    "GridDBApiKey": GsStrConfig(
        "SteamGridDB API Key",
        "官方封面均失败时用社区封面兜底；留空则不查询。[申请链接](https://www.steamgriddb.com/profile/preferences)",
        "",
        secret=True,
    ),
    "_PushDivider": GsDivider(
        "消息推送配置",
        "",
    ),
    "NotifySwitch": GsBoolConfig(
        "开启用户状态变化通知功能",
        "关闭后仍会轮询并记录，但不再推送",
        True,
    ),
    "PriceNotifySwitch": GsBoolConfig(
        "开启游戏降价通知功能",
        "关闭后仍会轮询并记录价格，但不再推送降价提醒",
        True,
    ),
    "NotifyTypes": GsListStrConfig(
        "全局开启通知类型",
        "关闭的类型不会推送，无论用户是否订阅",
        list(NOTIFY_KINDS),
        options=list(NOTIFY_KINDS),
    ),
    "DefaultNotifyTypes": GsListStrConfig(
        "用户绑定后默认开启通知类型",
        "绑定后自动为账号订阅这些通知类型",
        ["开始游戏"],
        options=list(NOTIFY_KINDS),
    ),
    "PushMode": GsStrConfig(
        "用户状态变化推送方式",
        "用户状态变化推送方式",
        DEFAULT_PUSH_MODE,
        options=list(PUSH_MODES),
    ),
    "PushImage": GsBoolConfig(
        "用户状态变化推送图片",
        "关闭后将不会请求游戏封面图片，只会有文字",
        True,
    ),
    "QueuePushGroup": GsBoolConfig(
        "探索队列结果群聊推送",
        "自动探索队列执行完毕后是否向对应群聊推送结果",
        True,
    ),
    "QueuePushPrivate": GsBoolConfig(
        "探索队列结果私聊推送",
        "自动探索队列执行完毕后是否私聊通知开启用户",
        False,
    ),
    "_AutomationDivider": GsDivider(
        "自动化和轮询配置",
        "",
    ),
    "PollInterval": GsIntConfig(
        "用户状态轮询间隔 (秒)",
        "用户状态轮询间隔，修改后重启 GsCore 生效",
        20,
    ),
    "AchievementInterval": GsIntConfig(
        "成就轮询间隔 (秒)",
        "仅对正在游戏的账号查询成就，修改后重启 GsCore 生效",
        300,
    ),
    "PricePollInterval": GsIntConfig(
        "游戏降价轮询间隔 (小时)",
        "降价轮询间隔，修改后重启 GsCore 生效",
        2,
    ),
    "AnnouncePollInterval": GsIntConfig(
        "游戏公告轮询间隔 (小时)",
        "公告订阅的轮询间隔，修改后重启 GsCore 生效",
        1,
    ),
    "NotifyCD": GsIntConfig(
        "通知推送冷却 (分钟)",
        "同一账号在同一群聊的推送冷却，0 表示不启用",
        5,
    ),
    "QueueRounds": GsIntConfig(
        "每次探索队列轮数",
        "执行探索任务时每个账号执行的轮数",
        3,
    ),
    "QueueInterval": GsIntConfig(
        "探索队列轮次间隔 (秒)",
        "探索队列每轮之间的等待间隔",
        15,
    ),
    "CacheCleanDays": GsIntConfig(
        "全局缓存清理时间 (天)",
        "定时清理超过该天数的 Steam 数据缓存，0 表示不清理，修改后重启 GsCore 生效",
        3,
    ),
    "AutoQueueTime": GsTimeRConfig(
        "自动探索队列时间",
        "每日自动执行探索队列的时间 (时, 分)，修改后重启 GsCore 生效",
        (8, 0),
    ),
    "_OtherDivider": GsDivider(
        "其他配置",
        "",
    ),
    "AllowAt": GsBoolConfig(
        "允许 @ 他人",
        "开启后可通过 @ 指定查看他人数据",
        False,
    ),
    "HideSteamID": GsBoolConfig(
        "隐藏 steamid / 好友码",
        "开启后在展示好友码时隐藏中间数字",
        False,
    ),
    "CustomBgPath": GsImageConfig(
        "自定义背景",
        "卡片底图使用的自定义背景图；上传后自动生效，未上传时使用插件默认背景",
        "",
        str(DATA_DIR),
        "bg",
        "jpg",
    ),
    "CardUseProfileBg": GsBoolConfig(
        "卡片使用用户个人资料背景",
        "开启后卡片底图优先用目标账号的个人资料背景",
        False,
    ),
}


SteamConfig = StringConfig("SteamUID", CONFIG_PATH, CONFIG_DEFAULT)
