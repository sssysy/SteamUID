# -*- coding: utf-8 -*-
"""账号 token 生命周期：刷新 access_token、构建/校验商店会话。"""
import json
import time
from typing import Optional

import httpx
from gsuid_core.logger import logger

from ..database.models import SteamNextAccount
from ...SteamConfig import SteamConfig
from .client import (
    STEAM_DOMAINS,
    get_proxy_dict,
    get_proxy_url,
    make_async_client,
)
from .endpoints import (
    API_BASE_DEFAULT,
    AUTH_GENERATE_ACCESS_TOKEN,
    STORE_ACCOUNT_HOME,
    STORE_BASE_DEFAULT,
)

__all__ = [
    "get_proxy_url",
    "get_proxy_dict",
    "get_account_session",
    "refresh_account_tokens",
    "get_valid_session",
    "get_valid_access_token",
    "is_private_data_allowed",
]


def is_private_data_allowed() -> bool:
    """检查是否开启「登录后允许展示私密数据」配置"""
    try:
        conf = SteamConfig.get_config("AllowPrivateDataWithAuth")
        if conf is not None and isinstance(conf.data, bool):
            return conf.data
    except Exception:
        pass
    return True


async def get_valid_access_token(
    steamid64: str, auto_refresh: bool = True
) -> Optional[str]:
    """获取有效 access_token，若无则尝试通过 refresh_token 刷新。"""
    acc = await SteamNextAccount.get_account(steamid64)
    if not acc:
        return None

    if acc.access_token:
        return acc.access_token

    if auto_refresh and acc.refresh_token:
        if await refresh_account_tokens(steamid64):
            acc = await SteamNextAccount.get_account(steamid64)
            if acc and acc.access_token:
                return acc.access_token
    return None


async def get_account_session(steamid64: str) -> Optional[httpx.AsyncClient]:
    """根据 steamid64 从数据库构建带有已授权 Cookie 的 httpx.AsyncClient。"""
    acc = await SteamNextAccount.get_account(steamid64)
    if not acc:
        logger.warning(f"[SteamApi] 未找到账号 {steamid64} 的授权凭据")
        return None

    client = make_async_client(timeout=15)

    cookies: dict[str, str] = {}
    if acc.cookies_json:
        try:
            cookies = json.loads(acc.cookies_json)
        except Exception as e:
            logger.warning(f"[SteamApi] 解析账号 {steamid64} 的 Cookie 异常: {e}")

    session_id = acc.session_id or cookies.get("sessionid")
    if session_id:
        cookies["sessionid"] = str(session_id)

    if acc.access_token:
        cookies["steamLoginSecure"] = f"{steamid64}||{acc.access_token}"

    for domain in STEAM_DOMAINS:
        for name, value in cookies.items():
            client.cookies.set(name, str(value), domain=domain)

    return client


async def refresh_account_tokens(steamid64: str) -> bool:
    """使用 refresh_token 刷新账号的 access_token，并同步写回数据库。"""
    acc = await SteamNextAccount.get_account(steamid64)
    if not acc or not acc.refresh_token:
        logger.warning(f"[SteamApi] 账号 {steamid64} 不存在或无 refresh_token，无法刷新")
        return False

    url = f"{API_BASE_DEFAULT}{AUTH_GENERATE_ACCESS_TOKEN}"
    data = {
        "refresh_token": acc.refresh_token,
        "steamid": steamid64,
    }

    try:
        async with make_async_client(timeout=15) as client:
            resp = await client.post(url, data=data)
            if resp.status_code != 200:
                logger.error(f"[SteamApi] 刷新 token 请求失败: HTTP {resp.status_code}")
                return False

            res_json = resp.json()
            new_access_token = res_json.get("response", {}).get("access_token")
            if not new_access_token:
                logger.error(f"[SteamApi] 刷新 token 返回数据异常: {res_json}")
                return False

            cookies = {}
            if acc.cookies_json:
                try:
                    cookies = json.loads(acc.cookies_json)
                except Exception:
                    pass
            cookies["steamLoginSecure"] = f"{steamid64}||{new_access_token}"

            await SteamNextAccount.upsert_account(
                steamid64=steamid64,
                access_token=new_access_token,
                cookies_json=json.dumps(cookies, ensure_ascii=False),
                updated_at=int(time.time()),
            )
            logger.info(f"[SteamApi] 账号 {steamid64} access_token 自动刷新成功")
            return True
    except Exception as e:
        logger.error(f"[SteamApi] 刷新 token 过程出现异常: {e}")
        return False


async def get_valid_session(
    steamid64: str, auto_refresh: bool = True
) -> Optional[httpx.AsyncClient]:
    """获取有效且经过连通性校验的 Session，若失效且开启 auto_refresh 则自动刷新。"""
    session = await get_account_session(steamid64)
    if not session:
        return None

    try:
        test_url = f"{STORE_BASE_DEFAULT}{STORE_ACCOUNT_HOME}"
        resp = await session.get(test_url, timeout=10, follow_redirects=False)
        if resp.status_code in (302, 301) and "login" in resp.headers.get("Location", ""):
            if auto_refresh:
                logger.info(f"[SteamApi] 账号 {steamid64} 网页 Session 已失效，尝试刷新...")
                await session.aclose()
                if await refresh_account_tokens(steamid64):
                    return await get_account_session(steamid64)
            else:
                await session.aclose()
            return None
    except Exception as e:
        logger.warning(f"[SteamApi] 检验 session 有效性异常: {e}")

    return session
