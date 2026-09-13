from __future__ import annotations

import asyncio

import httpx
from gsuid_core.logger import logger


async def fetch_with_user_token(
    steamid64: str,
    url: str,
    params: dict,
    *,
    tag: str,
    timeout: float = 12.0,
) -> dict | None:
    """用用户的 access_token 取一次数 401/403 时自动刷新并重试一次。"""
    # 延迟导入：避免 utils.Api 与 utils.helpers 形成导入环
    from ..Api.account import (
        get_valid_access_token,
        is_private_data_allowed,
        refresh_account_tokens,
    )
    from ..Api.client import make_async_client

    if not is_private_data_allowed():
        return None

    token = await get_valid_access_token(steamid64)
    if not token:
        return None

    req_params = dict(params)
    req_params["access_token"] = token
    try:
        async with make_async_client(timeout=timeout) as client:
            resp = await client.get(url, params=req_params)
            if resp.status_code in (401, 403):
                logger.info(
                    f"[SteamUID] 账号 {steamid64} access_token 过期，尝试自动刷新..."
                )
                if await refresh_account_tokens(steamid64):
                    new_token = await get_valid_access_token(
                        steamid64, auto_refresh=False
                    )
                    if new_token:
                        req_params["access_token"] = new_token
                        resp = await client.get(url, params=req_params)
            if resp.status_code == 200:
                return resp.json()
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(f"[SteamUID] 凭据获取{tag}超时 steamid={steamid64}")
    except Exception as e:
        logger.warning(f"[SteamUID] 凭据获取{tag}异常 steamid={steamid64}: {e}")
    return None
