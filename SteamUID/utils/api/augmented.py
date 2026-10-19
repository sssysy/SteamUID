"""Augmented Steam 历史最低价查询，只取 Steam 商店当前地区数据。"""

from collections.abc import Sequence

import msgspec

from .client import make_async_client, request_ok_response
from .models import AugmentedGamePrices, AugmentedPricesResponse
from .endpoints import AUGMENTED_STORE_LOW_URL

_TAG = "史低查询"
_STEAM_SHOP_ID = 61


class AugmentedPricesRequest(msgspec.Struct):
    country: str
    apps: list[int]
    subs: list[int]
    bundles: list[int]
    voucher: bool
    shops: list[int]


async def fetch_store_lows(
    appids: Sequence[str],
    *,
    cc: str,
    proxy: str | None = None,
    timeout: float = 30.0,
) -> dict[str, AugmentedGamePrices]:
    """批量查询 Steam 商店史低；响应缺少的 appid 不伪造数据。"""
    normalized: list[int] = []
    for appid in appids:
        aid = str(appid).strip()
        if not aid.isdigit():
            raise ValueError(f"无效的 appid: {aid}")
        normalized.append(int(aid))
    if not normalized:
        return {}

    payload = AugmentedPricesRequest(
        country=cc,
        apps=normalized,
        subs=[],
        bundles=[],
        voucher=True,
        shops=[_STEAM_SHOP_ID],
    )
    body = msgspec.json.encode(payload)
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(
            client,
            "POST",
            AUGMENTED_STORE_LOW_URL,
            tag=_TAG,
            content=body,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

    decoded = msgspec.json.decode(resp.content, type=AugmentedPricesResponse)
    prices = decoded["prices"] if "prices" in decoded else {}
    result: dict[str, AugmentedGamePrices] = {}
    for appid in appids:
        key = f"app/{appid}"
        if key in prices:
            result[appid] = prices[key]
    return result
