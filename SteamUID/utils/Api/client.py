# -*- coding: utf-8 -*-
from typing import Optional

import httpx

from ...SteamConfig import SteamConfig

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)

DEFAULT_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"

STEAM_DOMAINS = [
    "store.steampowered.com",
    "help.steampowered.com",
    "steamcommunity.com",
]


def get_proxy_url() -> Optional[str]:
    """从 SteamConfig 获取配置的代理 URL"""
    try:
        val = SteamConfig.get_config("HttpProxy").data
        if isinstance(val, str):
            proxy = val.strip()
            if proxy:
                if not proxy.startswith(
                    ("http://", "https://", "socks5://", "socks5h://")
                ):
                    proxy = f"http://{proxy}"
                return proxy
    except Exception:
        pass
    return None


def get_proxy_dict() -> Optional[dict]:
    """从 SteamConfig 获取配置的代理字典（保留兼容性）"""
    proxy = get_proxy_url()
    if proxy:
        return {"http": proxy, "https": proxy}
    return None


def make_async_client(
    headers: Optional[dict] = None,
    timeout: float = 15.0,
    cookies: Optional[dict] = None,
) -> httpx.AsyncClient:
    """统一的 httpx.AsyncClient 工厂：自动挂代理与默认 UA。"""
    base_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
    }
    if headers:
        base_headers.update(headers)
    return httpx.AsyncClient(
        headers=base_headers,
        proxy=get_proxy_url(),
        timeout=timeout,
        cookies=cookies,
    )
