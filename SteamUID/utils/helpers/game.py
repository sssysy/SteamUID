"""游戏元数据解析与用户输入解析。"""

from __future__ import annotations

import json

from gsuid_core.bot import Bot

from ..Api import search_game_store
from ..database.models_cache import SteamApiCache
from ..exceptions import SteamValidationError

# resolve_game_input 第三个返回值的取值：本次解析的匹配质量
MATCH_NONE = ""  # 输入为纯数字 AppID，未经搜索
MATCH_EXACT = "exact"  # 搜索命中 type == 'app' 的本体游戏
MATCH_FALLBACK = "fallback"  # 搜索结果中无本体游戏，退而使用首项


def total_playtime(game: dict) -> int:
    """取单款游戏的累计游玩分钟数。"""
    return game.get("playtime_forever", 0) or (
        game.get("playtime_windows_forever", 0)
        + game.get("playtime_mac_forever", 0)
        + game.get("playtime_linux_forever", 0)
        + game.get("playtime_deck_forever", 0)
    )


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


async def send_match_tip(
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
    await send_match_tip(bot, game_name, appid, match_quality)

    if parse_limit:
        return appid, limit
    return appid
