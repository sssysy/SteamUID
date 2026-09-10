# -*- coding: utf-8 -*-
"""Store 页面接口：CDKey 激活、探索队列（需已登录 cookie session）。"""
import asyncio

import httpx
from gsuid_core.logger import logger

from .endpoints import (
    STORE_BASE_DEFAULT,
    STORE_GENERATE_DISCOVERY_QUEUE,
    STORE_REGISTER_KEY,
)


class SteamStoreAuthExpiredError(Exception):
    """Store 登录凭据失效"""


async def register_cdkey(session: httpx.AsyncClient, cdk: str) -> dict:
    """
    激活一枚 CDKey。
    返回原始 JSON（含 purchase_result_details 等字段）；HTTP 非 200 时抛异常。
    """
    sessionid = session.cookies.get(
        "sessionid", domain="store.steampowered.com"
    ) or session.cookies.get("sessionid")
    url = f"{STORE_BASE_DEFAULT}{STORE_REGISTER_KEY}"
    data = {
        "product_key": cdk,
        "sessionid": sessionid,
    }
    headers = {
        "Referer": f"{STORE_BASE_DEFAULT}/account/registerkey/",
        "Origin": STORE_BASE_DEFAULT,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    resp = await session.post(url, data=data, headers=headers, timeout=15)
    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}",
            request=resp.request,
            response=resp,
        )
    return resp.json()


async def generate_discovery_queue(
    session: httpx.AsyncClient,
    store_base_url: str,
    session_id: str,
) -> list[int]:
    """生成/获取新探索队列，返回 appid 列表。"""
    gen_url = f"{store_base_url.rstrip('/')}{STORE_GENERATE_DISCOVERY_QUEUE}"
    headers = {
        "Origin": store_base_url,
        "Referer": f"{store_base_url.rstrip('/')}/explore/",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = await session.post(
        gen_url,
        data={"sessionid": session_id, "queuetype": "0"},
        headers=headers,
        timeout=15,
    )
    if resp.status_code in (401, 403):
        raise SteamStoreAuthExpiredError("登录凭证已失效，请重新登录")
    if resp.status_code != 200:
        raise Exception(f"生成探索队列异常 (HTTP {resp.status_code})")

    try:
        data = resp.json()
    except Exception:
        if "login" in str(resp.url) or "login" in resp.text:
            raise SteamStoreAuthExpiredError("登录凭证已失效，请重新登录")
        raise Exception("接口返回非有效 JSON 数据")

    queue = data.get("queue", [])
    if not isinstance(queue, list):
        return []
    return [int(x) for x in queue if str(x).isdigit()]


async def clear_discovery_queue_app(
    session: httpx.AsyncClient,
    store_base_url: str,
    session_id: str,
    appid: int,
):
    """提交清除单个队列游戏。"""
    app_url = f"{store_base_url.rstrip('/')}/app/{appid}"
    headers = {
        "Origin": store_base_url,
        "Referer": app_url,
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = await session.post(
        app_url,
        data={
            "sessionid": session_id,
            "appid_to_clear_from_queue": str(appid),
        },
        headers=headers,
        timeout=10,
    )
    if resp.status_code in (401, 403):
        raise SteamStoreAuthExpiredError("登录凭证已失效，请重新登录")
