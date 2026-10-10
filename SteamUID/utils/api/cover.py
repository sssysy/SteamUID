"""封面直链拼接与 SteamGridDB 社区封面查询。

只负责请求与直链拼接，缓存读写与候选挑选策略由调用方处理。
"""

from collections.abc import Sequence

from .client import make_async_client, request_ok_response
from .models import GridDbBatchEntry, GridDbBatchResponse, GridDbGridsResponse
from .endpoints import (
    GRIDDB_API_BASE,
    APP_ICON_TEMPLATE,
    COVER_VARIANT_PATHS,
    COVER_ASSET_TEMPLATE,
)

_TAG = "游戏封面"

# 锁定官方横板比例，并过滤成人内容与恶搞梗图
_GRIDDB_PARAMS: dict[str, str] = {
    "types": "static",
    "dimensions": "460x215,920x430",
    "nsfw": "false",
    "humor": "false",
}


def get_official_cover_url(appid: str | int, variant: str = "header") -> str:
    """拼官方 CDN 封面直链，variant 必须是已登记的类型。"""
    if variant not in COVER_VARIANT_PATHS:
        raise ValueError(f"不支持的封面类型: {variant}")
    return COVER_ASSET_TEMPLATE.format(appid=str(appid).strip(), variant=COVER_VARIANT_PATHS[variant])


def build_app_icon_url(appid: str | int, icon_hash: str) -> str:
    """拼 media 站的游戏小图标直链。"""
    return APP_ICON_TEMPLATE.format(appid=str(appid).strip(), icon_hash=icon_hash)


def _griddb_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "User-Agent": "SteamUID/1.0",
    }


async def fetch_griddb_grids(
    appid: str | int,
    *,
    api_key: str,
    proxy: str | None = None,
    timeout: float = 5.0,
) -> GridDbGridsResponse:
    """查单个游戏的社区封面候选，挑选哪张由调用方决定。"""
    aid = str(appid).strip()
    if not aid.isdigit():
        raise ValueError(f"无效的 appid: {aid}")

    url = f"{GRIDDB_API_BASE}/grids/steam/{aid}"
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(
            client,
            "GET",
            url,
            tag=_TAG,
            headers=_griddb_headers(api_key),
            params=_GRIDDB_PARAMS,
            timeout=timeout,
        )

    payload: GridDbGridsResponse = resp.json()
    return payload


async def fetch_griddb_grids_batch(
    appids: Sequence[str],
    *,
    api_key: str,
    proxy: str | None = None,
    timeout: float = 8.0,
) -> list[GridDbBatchEntry]:
    """批量查询社区封面，返回与请求顺序对齐的原始条目，207 视为部分成功。"""
    valid = [str(aid).strip() for aid in appids if str(aid).strip().isdigit()]
    if not valid:
        return []

    url = f"{GRIDDB_API_BASE}/grids/steam/{','.join(valid)}"
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(
            client,
            "GET",
            url,
            tag=_TAG,
            headers=_griddb_headers(api_key),
            params=_GRIDDB_PARAMS,
            timeout=timeout,
        )

    payload: GridDbBatchResponse = resp.json()
    return payload["data"] if "data" in payload else []
