# -*- coding: utf-8 -*-
"""愿望单增删指令：业务编排，协议调用走 utils/Api/wishlist。"""
import asyncio

import httpx
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.Api import add_to_wishlist, remove_from_wishlist
from ..utils.database.models import SteamBind, SteamNextAccount
from ..utils.exceptions import SteamValidationError
from ..utils.utils import resolve_game_input


async def _resolve_account_and_game(bot: Bot, ev: Event, tip_example: str):
    raw_text = ev.text.strip()
    if not raw_text:
        raise SteamValidationError(f"请输入游戏名或 AppID！例如：{tip_example}")

    steamid64 = await SteamBind.get_main_id(
        ev.bot_id, ev.user_id, ev.user_type, ev.group_id
    )
    if not steamid64:
        raise SteamValidationError(
            "未找到绑定的 Steam 账号，请先使用【steam绑定 <SteamID/好友代码>】进行绑定！"
        )

    acc = await SteamNextAccount.get_account(steamid64)
    if not acc or not acc.access_token:
        raise SteamValidationError(
            "未检测到该账号的登录授权，请先发送【steam登录】完成网页授权！"
        )

    appid, game_name, is_from_search = await resolve_game_input(raw_text)
    if is_from_search:
        await bot.send(
            f"猜你想找 {game_name}({appid})，如有错误请使用 appid 精确匹配游戏"
        )
    return acc.access_token, appid, game_name


def _format_api_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code if e.response is not None else None
        if status in (401, 403):
            return "Steam 登录授权已失效，请发送【steam登录】重新授权！"
        return f"操作失败：Steam API 返回 HTTP {status if status is not None else 'Error'}"
    if isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError)):
        return "操作失败：连接 Steam 超时，请检查网络或稍后重试！"
    return f"操作失败：{e}"


async def add_game_to_wishlist(bot: Bot, ev: Event) -> str:
    """添加游戏到愿望单"""
    try:
        access_token, appid, game_name = await _resolve_account_and_game(
            bot, ev, "steam添加愿望单 730 或 艾尔登法环"
        )
        await add_to_wishlist(access_token, int(appid))
        return f"已将【{game_name}】({appid}) 添加至愿望单~"
    except SteamValidationError:
        raise
    except Exception as e:
        logger.exception(f"[SteamWishListEdit] 添加愿望单异常: {e}")
        return _format_api_error(e)


async def remove_game_from_wishlist(bot: Bot, ev: Event) -> str:
    """从愿望单移出游戏"""
    try:
        access_token, appid, game_name = await _resolve_account_and_game(
            bot, ev, "steam删除愿望单 730 或 艾尔登法环"
        )
        await remove_from_wishlist(access_token, int(appid))
        return f"已将【{game_name}】({appid}) 从愿望单移除~"
    except SteamValidationError:
        raise
    except Exception as e:
        logger.exception(f"[SteamWishListEdit] 删除愿望单异常: {e}")
        return _format_api_error(e)
