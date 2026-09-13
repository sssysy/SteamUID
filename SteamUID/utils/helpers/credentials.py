"""凭据 Cookie 的统一写入入口，域名集合由调用方显式给出。"""

from __future__ import annotations

from typing import Sequence

import httpx


def apply_cookies(
    client: httpx.AsyncClient,
    cookies: dict,
    domains: Sequence[str],
) -> None:
    """把一组 Cookie 写到 ``client`` 的多个域名上。"""
    for domain in domains:
        for name, value in cookies.items():
            client.cookies.set(name, str(value), domain=domain)
