from typing import Sequence, overload
import time

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .api import resolve_game_input
from .database.models import SteamBind
from .downloader import download
from .exceptions import SteamValidationError
from ..SteamConfig import SteamConfig


@overload
async def resolve_target_appid(
    bot: Bot,
    text: str,
    parse_limit: bool = False,
    default_limit: int = 10,
) -> str: ...


@overload
async def resolve_target_appid(
    bot: Bot,
    text: str,
    parse_limit: bool = True,
    default_limit: int = 10,
) -> tuple[str, int]: ...


async def resolve_target_appid(
    bot: Bot,
    text: str,
    parse_limit: bool = False,
    default_limit: int = 10,
) -> str | tuple[str, int]:
    """从用户输入文本中解析出目标 AppID（支持纯数字 AppID 或游戏名称自动搜索）。

    如果通过游戏名称搜索匹配成功，会自动调用 `bot.send` 发送：
    '猜你想找 <游戏名>(appid)，如有错误请使用 appid 精确匹配游戏'

    Args:
        bot: Bot 实例，用于在搜索匹配成功时发送提示
        text: 用户输入的原始文本
        parse_limit: 是否解析末尾的条数 limit（用于排行榜等命令）
        default_limit: 默认条数（当 parse_limit=True 时生效）

    Returns:
        若 parse_limit=False: 返回 appid 字符串
        若 parse_limit=True: 返回 (appid, limit) 元组
    """
    raw_text = text.strip()
    if not raw_text:
        raise SteamValidationError("请输入游戏名或 AppID！例如：730 或 艾尔登法环")

    if not parse_limit:
        appid, game_name, is_from_search = await resolve_game_input(raw_text)
        if is_from_search:
            await bot.send(f"猜你想找 {game_name}({appid})，如有错误请使用 appid 精确匹配游戏")
        return appid

    words = raw_text.split()
    limit = default_limit
    game_query = raw_text

    # 处理带条数参数的情况（例如：730 5 或 艾尔登法环 5 或 Cyberpunk 2077 5）
    if len(words) >= 2 and words[-1].isdigit():
        possible_limit = int(words[-1])
        if words[0].isdigit() and len(words) == 2:
            game_query = words[0]
            if possible_limit > 0:
                limit = possible_limit
        elif 1 <= possible_limit <= 100:
            candidate_query = " ".join(words[:-1])
            try:
                appid, game_name, is_from_search = await resolve_game_input(candidate_query)
                if is_from_search:
                    await bot.send(f"猜你想找 {game_name}({appid})，如有错误请使用 appid 精确匹配游戏")
                return appid, possible_limit
            except Exception:
                game_query = raw_text

    appid, game_name, is_from_search = await resolve_game_input(game_query)
    if is_from_search:
        await bot.send(f"猜你想找 {game_name}({appid})，如有错误请使用 appid 精确匹配游戏")
    return appid, limit


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


async def resolve_target_steamid64(ev: Event, text: str = "") -> str | None:
    """三级回退：auto2steamid64(text) → @他人的主ID → 当前用户的主ID。
    注意：会修改 ev.user_id 以支持 @他人。
    """
    if ev.at:
        if not SteamConfig.get_config("AllowAt").data:
            raise SteamValidationError("未开启 @ 他人获取他人信息功能")
        ev.user_id = ev.at

    if text:
        steamid64 = auto2steamid64(text.strip())
        if steamid64:
            return steamid64

    return await SteamBind.get_main_id(
        ev.bot_id, ev.user_id, ev.user_type, ev.group_id
    )


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
    diff_sec = time.time() - float(timecreated)
    if diff_sec <= 0:
        return "0.0年"
    years = diff_sec / (365.25 * 86400)
    return f"{years:.1f}年"


PUSH_EVENTS: dict[str, str] = {
    "push_start_game": "开始游戏",
    "push_end_game": "结束游戏",
    "push_archivement": "获得成就",
}


def get_enabled_push_events() -> set[str]:
    return set(SteamConfig.get_config("PushSwitch").data)


def is_push_event_enabled(event_name: str) -> bool:
    return event_name in get_enabled_push_events()


def resolve_player_status(player: dict) -> tuple[str, str | None]:
    """返回 (status, game_name): ingame/offline/online"""
    if player.get("gameid"):
        return ("ingame", player.get("gameextrainfo", ""))
    if player.get("personastate", 0) == 0:
        return ("offline", None)
    return ("online", None)
