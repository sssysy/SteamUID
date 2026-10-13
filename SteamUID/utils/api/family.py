"""IFamilyGroupsService 家庭组与家庭共享库查询，凭据为 access_token。"""

from .client import make_async_client, request_ok_response
from .models import SharedLibraryAppsResponse, FamilyGroupForUserResponse
from .endpoints import (
    API_BASE_DEFAULT,
    FAMILY_GET_GROUP_FOR_USER,
    FAMILY_GET_SHARED_LIBRARY_APPS,
)

_TAG = "家庭库"


async def get_family_group_for_user(
    steamid: str,
    *,
    access_token: str,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 10.0,
) -> FamilyGroupForUserResponse:
    """查询账号所属家庭组；凭据失效时抛 httpx.HTTPStatusError。"""
    url = f"{base_url.rstrip('/')}{FAMILY_GET_GROUP_FOR_USER}"
    params = {"access_token": access_token, "steamid": steamid}

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: FamilyGroupForUserResponse = resp.json()
    return payload


async def get_shared_library_apps(
    family_groupid: str,
    steamid: str,
    *,
    access_token: str,
    include_own: bool = True,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> SharedLibraryAppsResponse:
    """查询家庭共享库应用列表，include_own 决定是否含自己拥有的游戏。"""
    url = f"{base_url.rstrip('/')}{FAMILY_GET_SHARED_LIBRARY_APPS}"
    params = {
        "access_token": access_token,
        "family_groupid": family_groupid,
        "steamid": steamid,
        "include_own": include_own,
    }

    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, params=params, timeout=timeout)

    payload: SharedLibraryAppsResponse = resp.json()
    return payload
