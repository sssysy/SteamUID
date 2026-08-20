import json
import asyncio
import httpx
from gsuid_core.logger import logger
from ..SteamConfig.interface import SteamAPI
from ..SteamConfig import SteamConfig
from .database.models_cache import SteamApiCache, SteamArchivementCache



async def get_user_Summaries(steamid64: str | list[str]) -> list:
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    if isinstance(steamid64, str):
        steamid64 = [steamid64]

    url = f"{base_url}{SteamAPI.api_GetPlayerSummaries}"

    # 分批，每批最多50个
    batches = [steamid64[i:i + 50] for i in range(0, len(steamid64), 50)]

    async def fetch_batch(client: httpx.AsyncClient, batch: list[str]) -> list:
        params = {"key": api_key, "steamids": ','.join(batch)}
        response = await client.get(url, params=params)
        data = response.json()
        return data.get("response", {}).get("players", [])

    async with httpx.AsyncClient(timeout=5) as client:
        tasks = [fetch_batch(client, batch) for batch in batches]
        results = await asyncio.gather(*tasks)

    # 合并所有批次结果
    all_players = []
    for players in results:
        all_players.extend(players)
    return all_players
    
async def get_game_info(appid: str) -> dict:
    """获取游戏详情（带缓存：命中缓存则不请求API）"""
    cached = await SteamApiCache.get_cache(appid)
    if cached is not None:
        return json.loads(cached)

    base_url = SteamConfig.get_config("storeBaseURL").data
    url = f"{base_url}{SteamAPI.store_GetGameDetails}"
    params = {
        "appids": appid,
        "l": "schinese",
    }
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(url, params=params)
        data = response.json()
        result = data.get(appid, {})

    if result:
        await SteamApiCache.upsert_cache(appid, json.dumps(result, ensure_ascii=False))
    return result
    
async def get_steamlibrary_by_steamid64(api_key: str, steamid64: str) -> dict:
    """取玩家游戏库"""
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetOwnedGames}"
    params = {
        "key": api_key,
        "steamid": steamid64,
        "include_appinfo": True,
        "include_played_free_games": True,
    }
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data.get("response", {})
    
async def get_archivement_info(appid: str, steamid64: str):
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetPlayerAchievements}"
    params = {
        "key": api_key,
        "appid": appid,
        "steamid": steamid64,
        "l": "schinese",
    }    
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data.get("playerstats", {})
    
async def get_archivement_img(appid: str, archivement_name: str) -> str:
    """获取单个成就的icon URL（复用 get_archivement_schema 缓存，不单独请求API）"""
    schema_list = await get_archivement_schema(appid)
    for archivement in schema_list:
        if archivement.get("name") == archivement_name:
            return archivement.get("icon", "")
    return ""

async def get_archivement_schema(appid: str) -> list[dict]:
    """一次性获取游戏成就 Schema（含 icon/icongray/displayName/description）。

    返回 game.availableGameStats.achievements 列表；无数据时返回空列表。
    带缓存：命中缓存则不请求API。供「游戏成就」命令和 get_archivement_img 共享使用。
    """
    cached = await SteamArchivementCache.get_cache(appid)
    if cached is not None:
        return json.loads(cached)

    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetSchemaForGame}"
    params = {
        "key": api_key,
        "appid": appid,
        "l": "schinese",
    }
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(url, params=params)
        data = response.json()
        achievements = data.get("game", {}).get("availableGameStats", {}).get("achievements", [])

    if achievements:
        await SteamArchivementCache.upsert_cache(appid, json.dumps(achievements, ensure_ascii=False))
    return achievements

async def get_price_data(appid: str | list[str]) -> dict:
    """获取游戏价格数据（支持单 AppID 或列表批量查询）"""
    base_url = SteamConfig.get_config("storeBaseURL").data
    cc = SteamConfig.get_config("pricecc").data

    if isinstance(appid, str):
        appid = [appid]

    url = f"{base_url}{SteamAPI.store_GetGameDetails}"

    # 分批，每批最多50个
    batches = [appid[i:i + 50] for i in range(0, len(appid), 50)]


    async def fetch_batch(client: httpx.AsyncClient, batch: list[str]) -> dict:
        try:
            params = {"appids": ','.join(batch), "cc": cc, "filters": "price_overview"}
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"[SteamUID] 批量获取游戏价格异常 batch={batch[:3]}...: {e}")
        return {}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [fetch_batch(client, batch) for batch in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 合并所有批次结果
    all_prices: dict = {}
    for res in results:
        if isinstance(res, dict):
            all_prices.update(res)
    return all_prices


async def get_profile_items_equipped(steamid64: str) -> dict:
    """获取玩家装备项（头像框/动画头像/迷你资料背景）"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetProfileItemsEquipped}"
    params = {"key": api_key, "steamid": steamid64, "l": "schinese"}
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data.get("response", {})


async def get_miniprofile(steamid64: str) -> dict:
    """获取 Steam miniprofile JSON 数据（等级/徽章/背景/头像）"""
    community_url = SteamConfig.get_config("CommunityBaseURL").data
    steamid32 = int(steamid64) - 76561197960265728
    url = f"{community_url}/miniprofile/{steamid32}/json"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, params={"l": "schinese"})
        return response.json()


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


