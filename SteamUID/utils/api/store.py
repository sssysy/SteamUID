"""商店网页接口：CDKey 激活与探索队列。

依赖调用方传入已登录的 httpx 会话，本模块不负责构建 / 校验会话。
"""

import httpx

from .client import request_ok_response
from .models import RegisterCdKeyResponse, DiscoveryQueueResponse
from .endpoints import (
    STORE_APP_PAGE,
    STORE_BASE_DEFAULT,
    STORE_REGISTER_KEY,
    STORE_GENERATE_DISCOVERY_QUEUE,
)

_TAG = "商店操作"


def _session_id(session: httpx.AsyncClient) -> str:
    """从会话 Cookie 中取 sessionid，取不到返回空串。"""
    for cookie in session.cookies.jar:
        if cookie.name == "sessionid" and cookie.value is not None:
            return cookie.value
    return ""


async def register_cdkey(
    session: httpx.AsyncClient,
    cdk: str,
    *,
    base_url: str = STORE_BASE_DEFAULT,
    timeout: float = 15.0,
) -> RegisterCdKeyResponse:
    """激活一枚 CDKey，返回原始结果体，结果码解释由调用方处理。"""
    base = base_url.rstrip("/")
    url = f"{base}{STORE_REGISTER_KEY}"
    headers = {
        "Referer": f"{base}/account/registerkey/",
        "Origin": base,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    resp = await request_ok_response(
        session,
        "POST",
        url,
        tag=_TAG,
        data={"product_key": cdk, "sessionid": _session_id(session)},
        headers=headers,
        timeout=timeout,
    )
    payload: RegisterCdKeyResponse = resp.json()
    return payload


async def generate_discovery_queue(
    session: httpx.AsyncClient,
    *,
    session_id: str,
    base_url: str = STORE_BASE_DEFAULT,
    timeout: float = 15.0,
) -> list[int]:
    """生成新的探索队列，返回原始 appid 列表。"""
    base = base_url.rstrip("/")
    url = f"{base}{STORE_GENERATE_DISCOVERY_QUEUE}"
    headers = {
        "Origin": base,
        "Referer": f"{base}/explore/",
        "X-Requested-With": "XMLHttpRequest",
    }

    resp = await request_ok_response(
        session,
        "POST",
        url,
        tag=_TAG,
        data={"sessionid": session_id, "queuetype": "0"},
        headers=headers,
        timeout=timeout,
    )

    payload: DiscoveryQueueResponse = resp.json()
    return payload["queue"] if "queue" in payload else []


async def clear_discovery_queue_app(
    session: httpx.AsyncClient,
    appid: int,
    *,
    session_id: str,
    base_url: str = STORE_BASE_DEFAULT,
    timeout: float = 10.0,
) -> None:
    """把单个游戏从探索队列中清除。"""
    base = base_url.rstrip("/")
    app_url = f"{base}{STORE_APP_PAGE.format(appid=appid)}"
    headers = {
        "Origin": base,
        "Referer": app_url,
        "X-Requested-With": "XMLHttpRequest",
    }

    await request_ok_response(
        session,
        "POST",
        app_url,
        tag=_TAG,
        data={"sessionid": session_id, "appid_to_clear_from_queue": str(appid)},
        headers=headers,
        timeout=timeout,
    )
