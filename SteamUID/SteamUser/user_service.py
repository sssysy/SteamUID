import json
import httpx
from gsuid_core.logger import logger

from ..SteamConfig import SteamConfig
from ..utils.api import (
    get_user_Summaries,
    get_miniprofile,
    get_profile_items_equipped,
    get_price_data,
    clear_user_mem_cache,
)
from ..utils.database.models_cache import SteamApiCache


async def refresh_user_cache(steamids: list[str]) -> int:
    """清除并强制重新请求指定的 steamid64 用户信息缓存（支持批量）"""
    import asyncio

    if not steamids:
        return 0

    # 1. 先清除指定用户的所有内存缓存
    for sid in steamids:
        await clear_user_mem_cache(sid)

    # 2. 批量重新拉取玩家摘要并缓存
    await get_user_Summaries(steamids)

    # 3. 并发拉取 miniprofile 与 profile_items_equipped
    tasks = []
    for sid in steamids:
        tasks.append(get_miniprofile(sid))
        tasks.append(get_profile_items_equipped(sid))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    return len(steamids)


async def get_player_bio(steamid64: str) -> str:
    """获取玩家 Steam 个人资料简介（从 Steam 社区 XML/HTML 解析）"""
    community_url = SteamConfig.get_config("CommunityBaseURL").data
    url = f"{community_url}/profiles/{steamid64}/?xml=1"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.text:
                import xml.etree.ElementTree as ET
                import re

                try:
                    root = ET.fromstring(resp.text)
                    summary = root.findtext("summary")
                    if summary:
                        clean_text = re.sub(r"<br\s*/?>", " ", summary)
                        clean_text = re.sub(r"<[^>]+>", "", clean_text)
                        return clean_text.strip()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[SteamUID] 获取个人简介失败: {e}")
    return ""


async def calculate_account_value(games: list[dict]) -> int:
    """根据拥有的游戏列表计算账号总价值（人民币元）"""
    if not games:
        return 0
    appids = [str(g.get("appid")) for g in games if g.get("appid")]
    if not appids:
        return 0

    uncached_appids = []
    total_cents = 0
    for appid in appids:
        cached = await SteamApiCache.get_cache(appid)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, dict):
                    item_data = data.get("data") if "data" in data else data
                    if isinstance(item_data, dict):
                        price_overview = item_data.get("price_overview")
                        if isinstance(price_overview, dict):
                            price = price_overview.get("initial", price_overview.get("final", 0))
                            total_cents += price
                continue
            except Exception:
                pass
        uncached_appids.append(appid)

    if uncached_appids:
        try:
            batch_prices = await get_price_data(uncached_appids)
            for appid, item in batch_prices.items():
                if isinstance(item, dict):
                    # 缓存已查询结果（包括免费游戏，避免重复查询）
                    await SteamApiCache.upsert_cache(appid, json.dumps(item, ensure_ascii=False))
                    if item.get("success"):
                        item_data = item.get("data")
                        if isinstance(item_data, dict):
                            price_overview = item_data.get("price_overview")
                            if isinstance(price_overview, dict):
                                price = price_overview.get("initial", price_overview.get("final", 0))
                                total_cents += price
        except Exception as e:
            logger.warning(f"[SteamUID] 计算账号价值查询价格失败: {e}")

    return int(round(total_cents / 100))
