from typing import Sequence
from .downloader import download


async def batch_download_images(
    urls: Sequence[str],
    save_dir: str,
    max_concurrency: int = 5,
) -> list[str | None]:
    """批量下载图片（向下兼容封装，底层使用 downloader.download）"""
    paths = await download(urls, save_dir=save_dir, max_concurrency=max_concurrency)
    return [str(p) if p is not None else None for p in paths]


_BASE_STEAM_ID64 = 76561197960265728


def steamid64_to_friend_code(steamid64: str) -> str:
    """将 steamid64 转换为好友码（账号ID）"""
    return str(int(steamid64) - _BASE_STEAM_ID64)


def auto2steamid64(count: str | None) -> str | None:
    """把好友码/steamid64自动变化成steamid64"""
    if count is None or count.strip() == "" or not count.isdigit():
        return None
    count = count.strip()
    if int(count) < _BASE_STEAM_ID64:
        count = str(_BASE_STEAM_ID64 + int(count))
    return count

def HideStr(text: str) -> str:
    """12345678 -> 1*****78"""
    if len(text) < 4:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 3) + text[-2:]


def time_convert_s(seconds: int) -> str:
    """将秒数转换为人类可读的时长，如 1天2小时30分45秒"""
    if seconds < 0:
        seconds = 0
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分")
    if secs > 0 or not parts:
        parts.append(f"{secs}秒")
    return "".join(parts)


def maybe_hide_steamid(text: str) -> str:
    """根据 HideSteamID 配置决定是否对 steamid / 好友码套用 HideStr"""
    from ..SteamConfig import SteamConfig
    if SteamConfig.get_config("HideSteamID").data:
        return HideStr(text)
    return text


async def get_user_group_nickname(
    bot_id: str, user_id: str, group_id: str | None
) -> str | None:
    """按 bot_id + user_id + group_id 从 CoreUser 表查询用户在该群的群昵称。

    group_id 为 None 或查询不到有效昵称时返回 None。
    """
    if not group_id:
        return None
    try:
        from gsuid_core.utils.database.models import CoreUser
        user = await CoreUser.base_select_data(
            bot_id=bot_id, user_id=user_id, group_id=group_id
        )
        if user is not None and user.user_name and user.user_name != "1":
            return str(user.user_name)
    except Exception as e:
        logger.warning(
            f"[SteamUID] 获取群昵称失败 "
            f"bot_id={bot_id} user_id={user_id} group_id={group_id}: {e!r}"
        )
    return None


def country_code_to_flag(code: str | None) -> str:
    """将两字母 ISO 国家代码转换为国旗 Emoji，若无效则返回未知"""
    if not code or len(code) != 2 or not code.isalpha():
        return "未知"
    return "".join(chr(127397 + ord(c.upper())) for c in code)


def calc_account_age(timecreated: int | None) -> str:
    """计算账号年限（如 8.2年），若无数据则返回 --"""
    if not timecreated or not isinstance(timecreated, (int, float)) or timecreated <= 0:
        return "--"
    import time
    diff_sec = time.time() - float(timecreated)
    if diff_sec <= 0:
        return "0.0年"
    years = diff_sec / (365.25 * 86400)
    return f"{years:.1f}年"

