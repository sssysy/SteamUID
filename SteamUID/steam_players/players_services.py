"""当前玩家命令：解析目标游戏并回执在线玩家数文案。"""

import httpx

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.api.public import get_number_of_current_players
from ..utils.helper.game import match_tip_text, resolve_game_ref
from ..utils.helper.config import api_base, region_cc, region_lang
from ..utils.helper.game_detail import resolve_game_name

_USAGE = "steam当前玩家 艾尔登法环 或 steam当前玩家 黑神话"


async def query_current_players(bot: Bot, ev: Event) -> None:
    """steam当前玩家(数)<游戏名/AppID>：取该游戏当前在线玩家数并文字回执。"""
    raw = ev.text.strip()
    if not raw:
        raise ValueError(f"请输入游戏名或 AppID，例如：{_USAGE}")

    ref = await resolve_game_ref(raw, cc=region_cc())
    if not raw.isdigit():
        await bot.send(match_tip_text(ref))

    name = await resolve_game_name(ref.appid, cc=region_cc(), lang=region_lang()) or ref.name
    try:
        payload = await get_number_of_current_players(ref.appid, base_url=api_base())
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise ValueError(f"未找到 AppID 为 {ref.appid} 的游戏") from error
        raise

    if "player_count" not in payload:
        raise ValueError("未取到该游戏的在线玩家数，可能该游戏暂不支持查询")
    await bot.send(f"游戏 {name} 当前玩家数为：{payload['player_count']}")
