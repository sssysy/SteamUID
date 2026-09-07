# -*- coding: utf-8 -*-
import asyncio
from typing import Optional
import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..SteamConfig import SteamConfig
from ..utils.database.models import SteamBind, SteamNextAccount
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.utils import resolve_game_input


def get_proxy_url() -> Optional[str]:
    """从 SteamConfig 获取配置的代理 URL"""
    try:
        val = SteamConfig.get_config("HttpProxy").data
        if isinstance(val, str):
            proxy = val.strip()
            if proxy:
                if not proxy.startswith(("http://", "https://", "socks5://", "socks5h://")):
                    proxy = f"http://{proxy}"
                return proxy
    except Exception:
        pass
    return None


async def _call_wishlist_api(action: str, access_token: str, appid: int) -> dict:
    """调用 Steam IWishlistService 异步接口"""
    url = f"https://api.steampowered.com/IWishlistService/{action}/v1"
    data = {
        "access_token": access_token,
        "appid": int(appid),
    }
    proxy = get_proxy_url()
    async with httpx.AsyncClient(proxy=proxy, timeout=15) as client:
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()


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
        await _call_wishlist_api("AddToWishlist", acc.access_token, int(appid))
        return f"已将【{game_name}】({appid}) 添加至愿望单~"
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            return "Steam 登录授权已失效，请发送【steam登录】重新授权！"
        return f"操作失败：Steam API 返回 HTTP {e.response.status_code if e.response is not None else 'Error'}"
    except (httpx.TimeoutException, asyncio.TimeoutError):
        return "操作失败：连接 Steam 超时，请检查网络或稍后重试！"
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
        await _call_wishlist_api("RemoveFromWishlist", acc.access_token, int(appid))
        return f"已将【{game_name}】({appid}) 从愿望单移除~"
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            return "Steam 登录授权已失效，请发送【steam登录】重新授权！"
        return f"操作失败：Steam API 返回 HTTP {e.response.status_code if e.response is not None else 'Error'}"
    except (httpx.TimeoutException, asyncio.TimeoutError):
        return "操作失败：连接 Steam 超时，请检查网络或稍后重试！"
    except Exception as e:
        logger.exception(f"[SteamNextWishList] 删除愿望单异常: {e}")
        return f"删除愿望单失败：{e}"
