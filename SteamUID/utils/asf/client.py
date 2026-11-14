"""ASF IPC 唯一 HTTP 传输入口，默认直连、不继承 Steam 正向代理。"""

from typing import Literal, TypedDict
from collections.abc import Mapping

import httpx

from gsuid_core.logger import logger

_TAG = "[Steam·ASF]"


class AsfEndpoint(TypedDict):
    base_url: str
    password: str


class AsfRequestError(RuntimeError):
    """ASF 返回非 2xx 或响应无法解析；只携带可展示摘要。"""


def _auth_headers(password: str) -> dict[str, str]:
    if not password:
        return {}
    return {"Authentication": password}


def _error_detail(response: httpx.Response) -> str:
    """错误详情只用状态码；响应正文可能含服务端内部信息，只进日志。"""
    return f"HTTP {response.status_code}"


async def request_asf(
    endpoint: AsfEndpoint,
    method: Literal["GET", "POST", "PUT", "DELETE"],
    path: str,
    *,
    params: Mapping[str, str | int | float | bool] | None = None,
    content: bytes | None = None,
    timeout: float = 10.0,
) -> httpx.Response:
    """发一次 ASF 请求；非 2xx 统一抛 AsfRequestError。"""
    url = f"{endpoint['base_url'].rstrip('/')}{path}"
    headers = _auth_headers(endpoint["password"])
    if content is not None:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
        response = await client.request(
            method,
            url,
            params=params,
            content=content,
        )

    if response.is_error:
        detail = _error_detail(response)
        logger.warning(f"{_TAG} 请求失败 {method} {path}: {detail}")
        logger.debug(f"{_TAG} 错误响应: {response.text}")
        raise AsfRequestError(f"ASF 请求失败：{detail}")
    return response
