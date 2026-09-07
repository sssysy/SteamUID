# -*- coding: utf-8 -*-
from typing import Optional
import requests
from steam.webapi import post as steam_post
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..SteamConfig import SteamConfig
from ..utils.database.models import SteamBind, SteamNextAccount
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.utils import resolve_game_input


def get_webapi_session() -> requests.Session:
    """构建用于 Steam WebAPI 的 Session，自动适配代理配置"""
    session = requests.Session()
    try:
        proxy = SteamConfig.get_config("HttpProxy").data.strip()
        if proxy:
            session.proxies.update({"http": proxy, "https": proxy})
    except Exception:
        pass
    return session


async def add_game_to_wishlist(bot: Bot, ev: Event) -> str:
    """添加游戏到愿望单"""
    raw_text = ev.text.strip()
    if not raw_text:
        raise SteamValidationError("请输入游戏名或 AppID！例如：steam添加愿望单 730 或 艾尔登法环")

    steamid64 = await SteamBind.get_main_id(ev.bot_id, ev.user_id, ev.user_type, ev.group_id)
    if not steamid64:
        raise SteamValidationError("未找到绑定的 Steam 账号，请先使用【steam绑定 <SteamID/好友代码>】进行绑定！")

    acc = await SteamNextAccount.get_account(steamid64)
    if not acc or not acc.access_token:
        raise SteamValidationError("未检测到该账号的登录授权，请先发送【steam登录】完成网页授权！")

    appid, game_name, is_from_search = await resolve_game_input(raw_text)
    if is_from_search:
        await bot.send(f"猜你想找 {game_name}({appid})，如有错误请使用 appid 精确匹配游戏")

    try:
        steam_post(
            "IWishlistService",
            "AddToWishlist",
            version=1,
            session=get_webapi_session(),
            params={
                "access_token": acc.access_token,
                "appid": int(appid),
            },
        )
        return f"已将【{game_name}】({appid}) 添加至愿望单~"
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            return "Steam 登录授权已失效，请发送【steam登录】重新授权！"
        return f"操作失败：Steam API 返回 HTTP {e.response.status_code if e.response is not None else 'Error'}"
    except Exception as e:
        logger.exception(f"[SteamNextWishList] 添加愿望单异常: {e}")
        return f"添加愿望单失败：{e}"


async def remove_game_from_wishlist(bot: Bot, ev: Event) -> str:
    """从愿望单移出游戏"""
    raw_text = ev.text.strip()
    if not raw_text:
        raise SteamValidationError("请输入游戏名或 AppID！例如：steam删除愿望单 730 或 艾尔登法环")

    steamid64 = await SteamBind.get_main_id(ev.bot_id, ev.user_id, ev.user_type, ev.group_id)
    if not steamid64:
        raise SteamValidationError("未找到绑定的 Steam 账号，请先使用【steam绑定 <SteamID/好友代码>】进行绑定！")

    acc = await SteamNextAccount.get_account(steamid64)
    if not acc or not acc.access_token:
        raise SteamValidationError("未检测到该账号的登录授权，请先发送【steam登录】完成网页授权！")

    appid, game_name, is_from_search = await resolve_game_input(raw_text)
    if is_from_search:
        await bot.send(f"猜你想找 {game_name}({appid})，如有错误请使用 appid 精确匹配游戏")

    try:
        steam_post(
            "IWishlistService",
            "RemoveFromWishlist",
            version=1,
            session=get_webapi_session(),
            params={
                "access_token": acc.access_token,
                "appid": int(appid),
            },
        )
        return f"已将【{game_name}】({appid}) 从愿望单移除~"
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            return "Steam 登录授权已失效，请发送【steam登录】重新授权！"
        return f"操作失败：Steam API 返回 HTTP {e.response.status_code if e.response is not None else 'Error'}"
    except Exception as e:
        logger.exception(f"[SteamNextWishList] 删除愿望单异常: {e}")
        return f"删除愿望单失败：{e}"
