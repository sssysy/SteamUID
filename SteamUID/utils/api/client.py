"""Steam HTTP 客户端与请求原语。

只负责组装 httpx.AsyncClient 与收发请求；配置层通过 provider 注入默认代理，
本模块不直接读取配置文件。
"""

from collections.abc import Mapping, Callable, Sequence

import httpx

from gsuid_core.logger import logger

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)

DEFAULT_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"

STEAM_DOMAINS: tuple[str, ...] = (
    "store.steampowered.com",
    "help.steampowered.com",
    "steamcommunity.com",
)

# Steam 商店的年龄门静态 Cookie，未携带时会拿到成人内容确认页而非数据
STEAM_STORE_COOKIES: dict[str, str] = {
    "birthtime": "786297601",
    "lastagecheckage": "1-0-1995",
    "wants_mature_content": "1",
}

_PROXY_SCHEMES = ("http://", "https://", "socks5://", "socks5h://")

ProxyProvider = Callable[[], str | None]

_proxy_provider: ProxyProvider | None = None


def set_proxy_provider(provider: ProxyProvider) -> None:
    """注册默认代理来源；未显式传 proxy 的客户端都由它解析。"""
    global _proxy_provider
    _proxy_provider = provider


def _default_proxy() -> str | None:
    return _proxy_provider() if _proxy_provider is not None else None


def normalize_proxy(raw: str | None) -> str | None:
    """把 host:port 形式的代理补成带 scheme 的 URL，空值返回 None。"""
    if raw is None:
        return None

    proxy = raw.strip()
    if not proxy:
        return None
    if proxy.startswith(_PROXY_SCHEMES):
        return proxy
    return f"http://{proxy}"


def make_async_client(
    *,
    proxy: str | None = None,
    timeout: float = 15.0,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    """统一客户端工厂：显式代理优先，未传时使用配置层注册的默认代理。"""
    merged_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
    }
    if headers is not None:
        merged_headers.update(headers)

    resolved_proxy = proxy if proxy is not None else _default_proxy()
    return httpx.AsyncClient(
        headers=merged_headers,
        proxy=normalize_proxy(resolved_proxy),
        timeout=timeout,
        cookies=dict(cookies) if cookies is not None else None,
        follow_redirects=follow_redirects,
    )


def apply_cookies(
    client: httpx.AsyncClient,
    cookies: Mapping[str, str],
    domains: Sequence[str] = STEAM_DOMAINS,
) -> None:
    """把同一组 Cookie 写到多个域名上，商店与社区需共享登录态。"""
    for domain in domains:
        for name, value in cookies.items():
            client.cookies.set(name, value, domain=domain)


async def request_response(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    tag: str,
    params: Mapping[str, str | int | float | bool] | None = None,
    data: Mapping[str, str | int | float] | None = None,
    content: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """发一次请求并原样返回响应，超时与网络错误由 httpx 原生抛出。"""
    resp = await client.request(
        method,
        url,
        params=params,
        data=data,
        content=content,
        headers=headers,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        logger.warning(f"[Steam·{tag}] 请求失败 HTTP {resp.status_code}: {url}")
    return resp


async def request_ok_response(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    tag: str,
    params: Mapping[str, str | int | float | bool] | None = None,
    data: Mapping[str, str | int | float] | None = None,
    content: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """在 request_response 之上要求 2xx，非 2xx 抛 httpx.HTTPStatusError。"""
    resp = await request_response(
        client,
        method,
        url,
        tag=tag,
        params=params,
        data=data,
        content=content,
        headers=headers,
        timeout=timeout,
    )

    resp.raise_for_status()
    return resp
