"""steamcmd.net PICS 公开元数据查询。

第三方 JSON 随用随请求，不落盘；字段提取由调用方处理。
"""

from .client import make_async_client, request_ok_response
from .models import PicsInfoResponse
from .endpoints import STEAMCMD_INFO_URL

_TAG = "构建信息"


async def get_app_info(
    appid: str,
    *,
    proxy: str | None = None,
    timeout: float = 20.0,
) -> PicsInfoResponse:
    """取 app 的 PICS 元数据原始响应。"""
    aid = str(appid).strip()
    if not aid.isdigit():
        raise ValueError(f"无效的 appid: {aid}")

    url = STEAMCMD_INFO_URL.format(appid=aid)
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, timeout=timeout)

    payload: PicsInfoResponse = resp.json()
    return payload
