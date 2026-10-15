"""Steam 令牌工具。

只做 access_token / refresh_token 的解析与换取，凭据落库 / 会话校验由调用方处理。
"""

import os
import json
from base64 import urlsafe_b64decode
from binascii import hexlify

from .client import make_async_client, request_ok_response
from .models import AccessTokenPayload, AccessTokenResponse
from .endpoints import API_BASE_DEFAULT, AUTH_GENERATE_ACCESS_TOKEN

_TAG = "账户令牌"


def generate_session_id() -> str:
    """生成 24 位十六进制字符串作为 sessionid。"""
    return hexlify(os.urandom(12)).decode("ascii")


def steamid_from_access_token(access_token: str) -> str:
    """从 access_token 的 JWT payload 取 steamid64(sub)；结构异常抛 ValueError。"""
    segments = access_token.split(".")
    if len(segments) < 2:
        raise ValueError("access_token 格式异常，无法解析 steamid")

    segment = segments[1]
    padded = segment + "=" * (-len(segment) % 4)
    try:
        raw = json.loads(urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("access_token 解析失败") from error

    if not isinstance(raw, dict) or "sub" not in raw:
        raise ValueError("access_token 缺少 sub 字段")
    sub = raw["sub"]
    if not isinstance(sub, str) or not sub.isdigit():
        raise ValueError("access_token 的 sub 不是合法 steamid64")
    return sub


async def generate_access_token_for_app(
    refresh_token: str,
    steamid: str,
    *,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> AccessTokenPayload:
    """用 refresh_token 换新的 access_token，响应缺 access_token 时抛 ValueError。

    服务端可能顺带轮换 refresh_token，调用方必须检查返回里有没有它并覆盖落库。
    """
    url = f"{base_url.rstrip('/')}{AUTH_GENERATE_ACCESS_TOKEN}"
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(
            client,
            "POST",
            url,
            tag=_TAG,
            data={"refresh_token": refresh_token, "steamid": steamid},
            timeout=timeout,
        )

    payload: AccessTokenResponse = resp.json()
    response = payload["response"]
    if "access_token" not in response:
        raise ValueError("刷新 access_token 返回数据异常")
    return response
