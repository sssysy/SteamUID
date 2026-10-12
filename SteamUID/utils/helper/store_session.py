"""商店登录会话：由授权账号行还原带登录态的 httpx 会话。

只负责凭据到会话的组装；是否已登录、失效后是否重试由调用方判断与编排。
"""

from dataclasses import dataclass

import httpx

from ..api.client import apply_cookies, make_async_client
from ..database.model_auth import SteamAuth

# Store 会话 Cookie 只写在商店域名上
STORE_DOMAIN = "store.steampowered.com"

_ACCEPT = "application/json, text/javascript, */*; q=0.01"
_TIMEOUT = 15.0


@dataclass(frozen=True)
class StoreSession:
    """已登录的商店会话；client 由调用方负责关闭。"""

    client: httpx.AsyncClient
    session_id: str


def has_store_credentials(account: SteamAuth) -> bool:
    """账号是否具备商店网页登录所需的 sessionid 与 access_token。"""
    return bool(account.session_id and account.access_token)


def make_store_session(account: SteamAuth) -> StoreSession:
    """按账号凭据组装商店会话；调用前应先用 has_store_credentials 判空。"""
    cookies = {
        "sessionid": account.session_id,
        "steamLoginSecure": f"{account.steamid64}||{account.access_token}",
    }
    client = make_async_client(headers={"Accept": _ACCEPT}, timeout=_TIMEOUT)
    apply_cookies(client, cookies, (STORE_DOMAIN,))
    return StoreSession(client=client, session_id=account.session_id)
