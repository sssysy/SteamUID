import asyncio
import json
import time
from typing import overload

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .api import (
    get_miniprofile,
    get_profile_items_equipped,
    get_user_Summaries,
    search_game_store,
)
from .database.models import SteamBind
from .database.models_cache import SteamApiCache
from .exceptions import SteamValidationError
from ..SteamConfig import SteamConfig


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


async def resolve_game_input(input_text: str) -> tuple[str, str, bool]:
    """解析用户输入的游戏标识（纯数字 AppID 或 游戏名称）。

    返回: (appid, game_name, is_from_search)
    - 若输入为纯数字 AppID: 返回 (appid, appid 或 从详情/缓存获取的游戏名, False)
    - 若输入为游戏名且搜索成功: 返回 (appid, 匹配到的游戏名, True)
    - 若未找到匹配游戏: 抛出 SteamValidationError
    """
    raw_input = input_text.strip()
    if not raw_input:
        raise SteamValidationError("请输入游戏名或 AppID！")

    # 1. 如果是纯数字，直接作为 AppID 处理
    if raw_input.isdigit():
        appid = raw_input
        # 尝试从缓存或详情中获取游戏名称以方便后续使用
        game_name = appid
        cached = await SteamApiCache.get_cache(appid)
        if cached:
            try:
                c_data = json.loads(cached)
                name = c_data.get("data", {}).get("name") if isinstance(c_data, dict) else None
                if name:
                    game_name = name
            except Exception:
                pass
        return appid, game_name, False

    # 2. 如果是非纯数字，调用官方商店搜索接口
    items = await search_game_store(raw_input)
    if not items:
        raise SteamValidationError(f"未找到与【{raw_input}】相关的游戏，请检查游戏名称或直接输入 AppID")

    # 优先选取 type == 'app'（本体游戏），避免优先匹配到 package/sub/bundle
    target_item = None
    for item in items:
        if item.get("type") == "app" and item.get("id") and item.get("name"):
            target_item = item
            break
    if target_item is None:
        target_item = items[0]

    matched_appid = str(target_item.get("id"))
    matched_name = str(target_item.get("name") or raw_input)
    return matched_appid, matched_name, True


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


async def get_user_static_avatar_frame(steamid64: str) -> str | None:
    """获取用户的静态 Steam 头像框 URL（优先 GetProfileItemsEquipped 静态小图，回退 miniprofile）"""
    try:
        items_data = await get_profile_items_equipped(steamid64)
        if isinstance(items_data, dict):
            frame = items_data.get("avatar_frame", {})
            if frame.get("image_small"):
                return f"https://shared.fastly.steamstatic.com/community_assets/images/{frame['image_small']}"
    except Exception as e:
        logger.debug(f"[SteamUID] 获取装备头像框异常 steamid={steamid64}: {e}")

    try:
        miniprofile_data = await get_miniprofile(steamid64)
        if isinstance(miniprofile_data, dict):
            frame_url = miniprofile_data.get("avatar_frame")
            if frame_url:
                return frame_url
    except Exception as e:
        logger.debug(f"[SteamUID] 获取miniprofile头像框异常 steamid={steamid64}: {e}")

    return None

