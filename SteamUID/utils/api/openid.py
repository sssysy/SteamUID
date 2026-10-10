"""Steam OpenID 2.0 登录协议原语。

只做协议拼接、回验与 steamid 解析，会话状态与网页路由由调用方处理。
"""

from urllib.parse import urlencode
from collections.abc import Mapping

from .client import request_response, make_async_client

OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"

_TAG = "账户绑定"


def build_login_url(return_to: str, realm: str) -> str:
    """拼接 Steam OpenID 登录跳转地址。"""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{OPENID_ENDPOINT}?{urlencode(params)}"


def extract_steamid64(params: Mapping[str, str]) -> str:
    """从回调参数解析 steamid64；缺失或非数字时回落空串。"""
    for key in ("openid.claimed_id", "openid.identity"):
        if key not in params:
            continue
        steamid = params[key].rstrip("/").rsplit("/", 1)[-1]
        if steamid.isdigit():
            return steamid
    return ""


async def verify_callback(params: Mapping[str, str], *, timeout: float = 10.0) -> bool:
    """把 openid.* 参数回传 Steam 做 check_authentication 验签。"""
    body = {key: value for key, value in params.items() if key.startswith("openid.")}
    if "openid.sig" not in body or "openid.signed" not in body:
        return False

    body["openid.mode"] = "check_authentication"
    async with make_async_client(timeout=timeout) as client:
        resp = await request_response(client, "POST", OPENID_ENDPOINT, tag=_TAG, data=body, timeout=timeout)

    return "is_valid:true" in resp.text
