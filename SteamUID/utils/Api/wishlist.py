# -*- coding: utf-8 -*-
"""IWishlistService：access_token 鉴权的愿写操作。"""
import asyncio

import httpx
from gsuid_core.logger import logger

from .client import make_async_client
from .endpoints import API_BASE_DEFAULT, WISHLIST_ADD, WISHLIST_REMOVE


async def _call_wishlist_api(path: str, access_token: str, appid: int) -> dict:
    url = f"{API_BASE_DEFAULT}{path}"
    data = {
        "access_token": access_token,
        "appid": int(appid),
    }
    async with make_async_client(timeout=15) as client:
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()


async def add_to_wishlist(access_token: str, appid: int) -> dict:
    """将游戏添加到愿望单。失败会抛 httpx 异常。"""
    try:
        return await _call_wishlist_api(WISHLIST_ADD, access_token, appid)
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.warning(f"[SteamApi] 添加愿望单超时 appid={appid}: {e}")
        raise
    except Exception as e:
        logger.warning(f"[SteamApi] 添加愿望单失败 appid={appid}: {e}")
        raise


async def remove_from_wishlist(access_token: str, appid: int) -> dict:
    """将游戏从愿望单移除。失败会抛 httpx 异常。"""
    try:
        return await _call_wishlist_api(WISHLIST_REMOVE, access_token, appid)
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.warning(f"[SteamApi] 移除愿望单超时 appid={appid}: {e}")
        raise
    except Exception as e:
        logger.warning(f"[SteamApi] 移除愿望单失败 appid={appid}: {e}")
        raise
