import asyncio
import json
import time
from typing import Sequence

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .Api import (
    get_miniprofile,
    get_profile_items_equipped,
    get_user_Summaries,
    search_game_store,
)
from .database.models import SteamBind, SteamIDInfo, SteamNextAccount
from .database.models_cache import SteamApiCache
from .downloader import download
from .exceptions import SteamValidationError
from .helpers.profile import resolve_profile_assets
from ..SteamConfig import SteamConfig


_BASE_STEAM_ID64 = 76561197960265728

# resolve_game_input 第三个返回值的取值：本次解析的匹配质量
MATCH_NONE = ""  # 输入为纯数字 AppID，未经搜索
MATCH_EXACT = "exact"  # 搜索命中 type == 'app' 的本体游戏
MATCH_FALLBACK = "fallback"  # 搜索结果中无本体游戏，退而使用首项


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


async def resolve_game_input(input_text: str) -> tuple[str, str, str]:
    """解析用户输入的游戏标识（纯数字 AppID 或 游戏名称）"""
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
        return appid, game_name, MATCH_NONE

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

    match_quality = MATCH_EXACT
    if target_item is None:
        target_item = items[0]
        match_quality = MATCH_FALLBACK

    matched_appid = str(target_item.get("id"))
    matched_name = str(target_item.get("name") or raw_input)
    return matched_appid, matched_name, match_quality


async def _send_match_tip(
    bot: Bot, game_name: str, appid: str, match_quality: str
) -> None:
    """搜索匹配到游戏时提示用户确认；退而使用首项时明确说明未精确匹配。"""
    if match_quality == MATCH_EXACT:
        await bot.send(f"猜你想找 {game_name}({appid})，如有错误请使用 appid 精确匹配游戏")
    elif match_quality == MATCH_FALLBACK:
        await bot.send(
            f"未精确匹配到本体游戏，已使用最接近的结果 {game_name}({appid})，"
            f"如有错误请使用 appid 精确匹配游戏"
        )


async def resolve_target_appid(
    bot: Bot,
    text: str,
    parse_limit: bool = False,
    default_limit: int = 10,
) -> str | tuple[str, int]:
    """从用户输入文本中解析出目标 AppID（支持纯数字 AppID 或游戏名称自动搜索）"""
    raw_text = text.strip()
    if not raw_text:
        raise SteamValidationError("请输入游戏名或 AppID！例如：730 或 艾尔登法环")

    limit = default_limit
    game_query = raw_text
    if parse_limit:
        words = raw_text.split()
        if len(words) >= 2 and words[-1].isdigit():
            limit = int(words[-1])
            game_query = " ".join(words[:-1])

    appid, game_name, match_quality = await resolve_game_input(game_query)
    await _send_match_tip(bot, game_name, appid, match_quality)

    if parse_limit:
        return appid, limit
    return appid


async def batch_download_images(
    urls: Sequence[str],
    save_dir: str,
    max_concurrency: int = 5,
) -> list[str | None]:
    """批量下载图片"""
    paths = await download(urls, save_dir=save_dir, max_concurrency=max_concurrency)
    return [str(p) if p is not None else None for p in paths]


async def resolve_target_steamid64(ev: Event, text: str = "") -> str | None:
    """解析查询目标"""
    owner_user_id = ev.user_id
    if ev.at:
        if not SteamConfig.get_config("AllowAt").data:
            raise SteamValidationError("未开启 @ 他人获取他人信息功能")
        owner_user_id = ev.at

    if text:
        steamid64 = auto2steamid64(text.strip())
        if steamid64:
            return steamid64

    return await SteamBind.get_main_id(
        ev.bot_id, owner_user_id, ev.user_type, ev.group_id
    )


def HideStr(text: str) -> str:
    """打码id"""
    if len(text) < 4:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 3) + text[-2:]


def time_convert_s(seconds: int) -> str:
    """将秒数转换为人类可读的时长"""
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
    """查询用户在该群的群昵称"""
    if not group_id:
        return None
    from gsuid_core.utils.database.models import CoreUser

    user = await CoreUser.base_select_data(
        bot_id=bot_id, user_id=user_id, group_id=group_id
    )
    if user is not None and user.user_name and user.user_name != "1":
        return str(user.user_name)
    return None


async def get_account_display_name(steamid64: str) -> str:
    """获取账号展示昵称：本地缓存 → 登录账号名 → 在线摘要"""
    user_info_raw = await SteamIDInfo.get_steamuserinfo(steamid64)
    if user_info_raw:
        try:
            info = json.loads(user_info_raw)
            if isinstance(info, dict) and info.get("personaname"):
                return str(info["personaname"])
        except Exception:
            pass

    try:
        acc = await SteamNextAccount.get_account(steamid64)
        if acc and acc.account_name:
            return str(acc.account_name)
    except Exception:
        pass

    try:
        summaries = await get_user_Summaries(steamid64)
        if summaries and isinstance(summaries, list) and summaries[0].get("personaname"):
            return str(summaries[0]["personaname"])
    except Exception:
        pass

    return "Steam用户"


def country_code_to_flag(code: str | None) -> str:
    """将两字母 ISO 国家代码转换为国旗"""
    if not code or len(code) != 2 or not code.isalpha():
        return "未知"
    return "".join(chr(127397 + ord(c.upper())) for c in code)


def calc_account_age(timecreated: int | None) -> str:
    """计算账号年限"""
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


async def get_user_static_avatar_frame(steamid64: str) -> str | None:
    """获取用户的静态 Steam 头像框 URL"""
    assets = await resolve_profile_assets(steamid64)
    return assets.avatar_frame_url


async def get_user_pill_data(steamid64: str) -> dict:
    """构建药丸型卡片所需的用户数据字典"""
    players_res, miniprofile_data, items_data = await asyncio.gather(
        get_user_Summaries(steamid64),
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        return_exceptions=True,
    )
    player = players_res[0] if (isinstance(players_res, list) and players_res) else {}

    assets = await resolve_profile_assets(
        steamid64,
        player=player,
        miniprofile_data=miniprofile_data,
        items_data=items_data,
    )

    return {
        "name": player.get("personaname", "未知用户"),
        "friend_code": steamid64_to_friend_code(steamid64),
        "avatar_url": assets.avatar_url,
        "avatar_frame_url": assets.avatar_frame_url,
        "bg_url": assets.bg_url,
    }
