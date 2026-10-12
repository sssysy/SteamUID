"""账号凭据取用：读库取 access_token、按需刷新回写，以及 401/403 时的一次换新重试。"""

import time
from typing import TypeVar
from collections.abc import Callable, Awaitable

import httpx

from gsuid_core.logger import logger

from ..api.auth import generate_access_token_for_app
from ..database.model_auth import SteamAuth

_TAG = "[Steam·账户令牌]"

_T = TypeVar("_T")


async def get_access_token(steamid64: str) -> str | None:
    """取库中已存的 access_token；无记录或无令牌返回 None。"""
    account = await SteamAuth.get_account(steamid64)
    if account is None or not account.access_token:
        return None
    return account.access_token


async def renew_access_token(steamid64: str) -> str | None:
    """用 refresh_token 换新 access_token 并回写；无 refresh_token 或换取失败返回 None。"""
    account = await SteamAuth.get_account(steamid64)
    if account is None or not account.refresh_token:
        return None

    try:
        token = await generate_access_token_for_app(account.refresh_token, steamid64)
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(f"{_TAG} 刷新 access_token 失败 steamid={steamid64}: {type(error).__name__}")
        return None

    await SteamAuth.upsert_account(
        steamid64=steamid64,
        account_name=account.account_name,
        access_token=token,
        refresh_token=account.refresh_token,
        session_id=account.session_id,
        cookies_json=account.cookies_json,
        updated_at=int(time.time()),
    )
    return token


def _is_unauthorized(error: httpx.HTTPStatusError) -> bool:
    """401/403 视为凭据失效；其余状态码交给调用方的错误边界处理。"""
    return error.response.status_code in (401, 403)


async def run_with_token(
    steamid64: str,
    call: Callable[[str], Awaitable[_T]],
) -> _T | None:
    """用该账号凭据执行调用：无凭据返回 None，401/403 换新后重试一次，仍失败返回 None。

    需要区分「未登录」与「授权失效」的调用方，先自行判断账号是否存有凭据。
    """
    token = await get_access_token(steamid64)
    # 只存了 refresh_token 的账号也要能用，先换一次再交给调用方判定失败
    if token is None:
        token = await renew_access_token(steamid64)
    if token is None:
        return None

    try:
        return await call(token)
    except httpx.HTTPStatusError as error:
        if not _is_unauthorized(error):
            raise
        logger.warning(f"{_TAG} 凭据调用未授权，尝试刷新 steamid={steamid64}")

    renewed = await renew_access_token(steamid64)
    if renewed is None:
        return None
    try:
        return await call(renewed)
    except httpx.HTTPStatusError as error:
        if not _is_unauthorized(error):
            raise
        logger.warning(f"{_TAG} 刷新后仍未授权 steamid={steamid64}")
        return None
