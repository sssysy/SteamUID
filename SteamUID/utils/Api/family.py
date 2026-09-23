"""Steam 家庭组 WebAPI：需账号 access_token，不走 Web API Key 池"""
import asyncio

import httpx
from gsuid_core.logger import logger

from ...SteamConfig import SteamConfig
from ...SteamConfig.interface import SteamAPI
from .account import get_valid_access_token, refresh_account_tokens
from .client import make_async_client


async def _family_get(steamid64: str, path: str, params: dict) -> dict | None:
    token = await get_valid_access_token(steamid64)
    if not token:
        return None

    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{path}"
    req_params = {**params, "access_token": token}

    try:
        async with make_async_client(timeout=15) as client:
            resp = await client.get(url, params=req_params)
            if resp.status_code in (401, 403):
                if await refresh_account_tokens(steamid64):
                    new_token = await get_valid_access_token(steamid64, auto_refresh=False)
                    if new_token:
                        req_params["access_token"] = new_token
                        resp = await client.get(url, params=req_params)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, dict) else None
            logger.warning(
                f"[SteamFamily] 请求家庭接口失败 steamid={steamid64} path={path} "
                f"status={resp.status_code}"
            )
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(f"[SteamFamily] 请求家庭接口超时 steamid={steamid64} path={path}")
    except Exception as e:
        logger.warning(f"[SteamFamily] 请求家庭接口异常 steamid={steamid64} path={path}: {e}")
    return None


async def get_family_group_for_user(steamid64: str) -> dict | None:
    """查询账号所在 Steam 家庭组信息；未加入或无登录态返回 None。"""
    data = await _family_get(
        steamid64,
        SteamAPI.api_FamilyGetGroupForUser,
        {
            "steamid": steamid64,
            "include_family_group_response": "true",
        },
    )
    if not data:
        return None
    response = data.get("response")
    return response if isinstance(response, dict) and response else None


async def get_shared_library_apps(steamid64: str, family_groupid: str) -> dict | None:
    """查询家庭共享库游戏列表。"""
    data = await _family_get(
        steamid64,
        SteamAPI.api_FamilyGetSharedLibraryApps,
        {
            "family_groupid": family_groupid,
            "steamid": steamid64,
            "include_own": "true",
        },
    )
    if not data:
        return None
    response = data.get("response")
    return response if isinstance(response, dict) else None
