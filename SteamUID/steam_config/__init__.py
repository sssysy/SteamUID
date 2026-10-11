"""SteamUID 插件配置项定义与注册。"""

from gsuid_core.logger import logger
from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsStrConfig,
    GsBoolConfig,
    GsIntConfig,
    GsListStrConfig,
)
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from ..utils.helper.status import (
    PUSH_MODES,
    PushOptions,
    NOTIFY_KINDS,
    DEFAULT_PUSH_MODE,
)

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
    "SteamAPIKey": GsListStrConfig(
        "Steam API Key",
        "前往 https://steamcommunity.com/dev/apikey 申请；用户状态轮询依赖它，可配置多个 Key 轮换",
        [],
        secret=True,
    ),
    "KeyPoolCooldown": GsIntConfig(
        "API Key 429 冷却 (秒)",
        "单个 Key 触发 429 后的冷却秒数",
        600,
    ),
    "NotifySwitch": GsBoolConfig(
        "开启用户状态变化通知",
        "关闭后仍会轮询并记录，但不再推送",
        True,
    ),
    "PollInterval": GsIntConfig(
        "用户状态轮询间隔 (秒)",
        "用户状态轮询间隔，修改后需重启 GsCore 生效",
        20,
    ),
    "AchievementInterval": GsIntConfig(
        "成就轮询间隔 (秒)",
        "仅对正在游戏的账号查询成就，修改后需重启 GsCore 生效",
        300,
    ),
    "NotifyCD": GsIntConfig(
        "通知推送冷却 (分钟)",
        "同一账号在同一群聊的推送冷却，0 表示不启用；私聊不受冷却限制",
        5,
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
        "分离为一条消息一个变化，合并为一条消息包含本轮全部变化",
        DEFAULT_PUSH_MODE,
        options=list(PUSH_MODES),
    ),
    "PushImage": GsBoolConfig(
        "用户状态变化推送图片",
        "关闭后卡片照常渲染，只是不请求游戏封面图",
        True,
    ),
    "AllowGridDBCover": GsBoolConfig(
        "允许备选 Grid DB 封面",
        "官方封面均失败时改用 SteamGridDB 社区封面兜底",
        False,
    ),
    "GridDBApiKey": GsStrConfig(
        "SteamGridDB API Key",
        "官方封面均失败时用社区封面兜底；留空则不查询。申请：https://www.steamgriddb.com/profile/preferences",
        "",
        secret=True,
    ),
    "CacheCleanDays": GsIntConfig(
        "全局缓存清理时间 (天)",
        "定时清理超过该天数的 Steam 数据缓存，0 表示不清理，修改后需重启 GsCore 生效",
        3,
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


def get_api_keys() -> list[str]:
    """配置的 Steam API Key 列表。"""
    config = SteamConfig.get_config("SteamAPIKey")
    if not isinstance(config, GsListStrConfig):
        logger.error("[Steam·密钥池] 配置项 SteamAPIKey 类型异常")
        return []
    return list(config.data)


def get_key_cooldown() -> int:
    """单 Key 触发 429 后的冷却秒数。"""
    config = SteamConfig.get_config("KeyPoolCooldown")
    if not isinstance(config, GsIntConfig):
        logger.error("[Steam·密钥池] 配置项 KeyPoolCooldown 类型异常")
        return 600
    return config.data


def get_notify_switch() -> bool:
    """是否开启用户状态变化通知。"""
    config = SteamConfig.get_config("NotifySwitch")
    if not isinstance(config, GsBoolConfig):
        logger.error("[Steam·状态轮询] 配置项 NotifySwitch 类型异常")
        return True
    return config.data


def get_poll_interval() -> int:
    """用户状态轮询间隔 (秒)。"""
    config = SteamConfig.get_config("PollInterval")
    if not isinstance(config, GsIntConfig):
        logger.error("[Steam·状态轮询] 配置项 PollInterval 类型异常")
        return 20
    return config.data


def get_achievement_interval() -> int:
    """成就轮询间隔 (秒)。"""
    config = SteamConfig.get_config("AchievementInterval")
    if not isinstance(config, GsIntConfig):
        logger.error("[Steam·成就轮询] 配置项 AchievementInterval 类型异常")
        return 300
    return config.data


def get_notify_cd() -> int:
    """通知推送冷却 (分钟)。"""
    config = SteamConfig.get_config("NotifyCD")
    if not isinstance(config, GsIntConfig):
        logger.error("[Steam·状态轮询] 配置项 NotifyCD 类型异常")
        return 5
    return config.data


def get_notify_types() -> list[str]:
    """全局开启的通知类型。"""
    config = SteamConfig.get_config("NotifyTypes")
    if not isinstance(config, GsListStrConfig):
        logger.error("[Steam·状态轮询] 配置项 NotifyTypes 类型异常")
        return list(NOTIFY_KINDS)
    return list(config.data)


def get_default_notify_types() -> list[str]:
    """用户绑定后默认开启的通知类型。"""
    config = SteamConfig.get_config("DefaultNotifyTypes")
    if not isinstance(config, GsListStrConfig):
        logger.error("[Steam·状态轮询] 配置项 DefaultNotifyTypes 类型异常")
        return ["开始游戏"]
    return list(config.data)


def get_push_mode() -> str:
    """状态变化推送方式；取值不在词表内时回落默认。"""
    config = SteamConfig.get_config("PushMode")
    if not isinstance(config, GsStrConfig):
        logger.error("[Steam·状态轮询] 配置项 PushMode 类型异常")
        return DEFAULT_PUSH_MODE
    if config.data not in PUSH_MODES:
        logger.error(f"[Steam·状态轮询] 配置项 PushMode 取值异常，已回落默认: {config.data}")
        return DEFAULT_PUSH_MODE
    return config.data


def get_push_image() -> bool:
    """是否获取游戏封面图。"""
    config = SteamConfig.get_config("PushImage")
    if not isinstance(config, GsBoolConfig):
        logger.error("[Steam·状态轮询] 配置项 PushImage 类型异常")
        return True
    return config.data


def get_griddb_key() -> str:
    """SteamGridDB API Key；未配置返回空串。"""
    config = SteamConfig.get_config("GridDBApiKey")
    if not isinstance(config, GsStrConfig):
        logger.error("[Steam·状态轮询] 配置项 GridDBApiKey 类型异常")
        return ""
    return config.data.strip()


def get_allow_griddb_cover() -> bool:
    """是否允许用 SteamGridDB 社区封面兜底。"""
    config = SteamConfig.get_config("AllowGridDBCover")
    if not isinstance(config, GsBoolConfig):
        logger.error("[Steam·状态轮询] 配置项 AllowGridDBCover 类型异常")
        return False
    return config.data


def get_cache_clean_days() -> int:
    """SteamCache 全局缓存清理天数；0 表示不清理。"""
    config = SteamConfig.get_config("CacheCleanDays")
    if not isinstance(config, GsIntConfig):
        logger.error("[Steam·缓存清理] 配置项 CacheCleanDays 类型异常")
        return 3
    return config.data


def get_push_options() -> PushOptions:
    """汇总一次推送所需的全部配置项。"""
    return PushOptions(
        kinds=frozenset(get_notify_types()),
        cd_seconds=get_notify_cd() * 60,
        mode=get_push_mode(),
        with_cover=get_push_image(),
        # 总开关关闭时清空 key，等价于不查询 GridDB
        griddb_key=get_griddb_key() if get_allow_griddb_cover() else "",
    )
