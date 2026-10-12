"""IWishlistService 愿望单读写：查询可用 key 或 access_token，增删需 access_token。"""

from .client import make_async_client, request_ok_response
from .models import WishlistItem, WishlistResponse, WishlistMutationResponse
from .endpoints import WISHLIST_ADD, WISHLIST_REMOVE, API_BASE_DEFAULT, API_GET_WISHLIST

_TAG = "愿望单"


async def get_wishlist_with_token(
    steamid: str,
    *,
    access_token: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> list[WishlistItem]:
    """用账号凭据查询本人愿望单（能读私密）；凭据失效时抛 httpx.HTTPStatusError。"""
    url = f"{base_url.rstrip('/')}{API_GET_WISHLIST}"
    params = {"access_token": access_token, "steamid": steamid}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: WishlistResponse = resp.json()
    response = payload["response"]
    return response["items"] if "items" in response else []


async def _call_wishlist_api(
    path: str,
    access_token: str,
    appid: int,
    *,
    base_url: str,
    proxy: str | None,
    timeout: float,
) -> WishlistMutationResponse:
    url = f"{base_url.rstrip('/')}{path}"
    data = {"access_token": access_token, "appid": str(appid)}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "POST", url, tag=_TAG, data=data, timeout=timeout)

    payload: WishlistMutationResponse = resp.json()
    return payload


async def add_to_wishlist(
    access_token: str,
    appid: int,
    *,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> WishlistMutationResponse:
    """把游戏加入愿望单。"""
    return await _call_wishlist_api(
        WISHLIST_ADD,
        access_token,
        appid,
        base_url=base_url,
        proxy=proxy,
        timeout=timeout,
    )


async def remove_from_wishlist(
    access_token: str,
    appid: int,
    *,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> WishlistMutationResponse:
    """把游戏移出愿望单。"""
    return await _call_wishlist_api(
        WISHLIST_REMOVE,
        access_token,
        appid,
        base_url=base_url,
        proxy=proxy,
        timeout=timeout,
    )
