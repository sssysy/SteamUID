import json
import asyncio
import time
import httpx
from gsuid_core.logger import logger
from ..SteamConfig.interface import SteamAPI
from ..SteamConfig import SteamConfig, get_current_cc, get_current_lang
from .database.models_cache import SteamApiCache, SteamArchivementCache

# 内存 TTL 缓存字典及锁
# key -> (data, expire_at)
_MEM_CACHE: dict[str, tuple[any, float]] = {}
_CACHE_LOCK = asyncio.Lock()


def get_default_cache_ttl() -> float:
    """根据 SteamConfig 中的 CacheTime (天) 动态转换为缓存秒数，默认最低 180 秒"""
    try:
        days = SteamConfig.get_config("CacheTime").data
        if isinstance(days, (int, float)) and days > 0:
            return float(days * 86400)
    except Exception:
        pass
    return 180.0


async def get_from_mem_cache(key: str) -> any:
    async with _CACHE_LOCK:
        item = _MEM_CACHE.get(key)
        if item is not None:
            data, expire_at = item
            if time.time() < expire_at:
                return data
            else:
                _MEM_CACHE.pop(key, None)
    return None


async def set_to_mem_cache(key: str, data: any, ttl_seconds: float | None = None) -> None:
    if ttl_seconds is None:
        ttl_seconds = get_default_cache_ttl()
    async with _CACHE_LOCK:
        _MEM_CACHE[key] = (data, time.time() + ttl_seconds)


async def clear_user_mem_cache(steamid64: str) -> None:
    """清除指定 steamid64 的个人资料内存缓存"""
    keys_to_delete = [
        f"profile_items_{steamid64}",
        f"miniprofile_{steamid64}",
    ]
    async with _CACHE_LOCK:
        for k in keys_to_delete:
            _MEM_CACHE.pop(k, None)


async def get_user_Summaries(steamid64: str | list[str]) -> list:
    """获取玩家摘要数据（支持单 ID 或列表，即时请求不使用缓存）"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    if isinstance(steamid64, str):
        steamids = [steamid64]
    else:
        steamids = list(steamid64)

    if not steamids:
        return []

    url = f"{base_url}{SteamAPI.api_GetPlayerSummaries}"
    batches = [steamids[i:i + 50] for i in range(0, len(steamids), 50)]

    async def fetch_batch(client: httpx.AsyncClient, batch: list[str]) -> list:
        try:
            params = {"key": api_key, "steamids": ','.join(batch)}
            response = await client.get(url, params=params)
            data = response.json()
            return data.get("response", {}).get("players", [])
        except Exception as e:
            logger.warning(f"[SteamUID] 获取玩家摘要失败 batch={batch[:3]}: {e}")
            return []

    async with httpx.AsyncClient(timeout=5) as client:
        tasks = [fetch_batch(client, batch) for batch in batches]
        results = await asyncio.gather(*tasks)

    all_players: list[dict] = []
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
        "l": get_current_lang(),
    }
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(url, params=params)
        data = response.json()
        result = data.get(appid, {}) if isinstance(data, dict) else {}

    if result:
        await SteamApiCache.upsert_cache(appid, json.dumps(result, ensure_ascii=False))
    return result


async def get_game_icon_url(appid: str, steamid64: str | None = None) -> str:
    """获取游戏的小图标（客户端小logo）URL"""
    if steamid64:
        try:
            api_key = SteamConfig.get_config("SteamWebAPIKey").data
            base_url = SteamConfig.get_config("APIBaseURL").data
            url = f"{base_url}{SteamAPI.api_GetOwnedGames}"
            params = {
                "key": api_key,
                "steamid": steamid64,
                "include_appinfo": True,
                "appids_filter[0]": appid,
            }
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    games = response.json().get("response", {}).get("games", [])
                    if games and games[0].get("img_icon_url"):
                        icon_hash = games[0]["img_icon_url"]
                        return f"https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{icon_hash}.jpg"
        except Exception:
            pass
    return f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_sm_120.jpg"


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
    """获取玩家指定游戏的成就信息"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetPlayerAchievements}"
    params = {
        "key": api_key,
        "appid": appid,
        "steamid": steamid64,
        "l": get_current_lang(),
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
        "l": get_current_lang(),
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
    cc = get_current_cc()

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


async def get_profile_items_equipped(steamid64: str, ttl_seconds: float | None = None) -> dict:
    """获取玩家装备项（头像框/动画头像/迷你资料背景，带根据设置 CacheTime 的内存 TTL 缓存）"""
    cache_key = f"profile_items_{steamid64}"
    cached = await get_from_mem_cache(cache_key)
    if cached is not None:
        return cached

    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetProfileItemsEquipped}"
    params = {"key": api_key, "steamid": steamid64, "l": get_current_lang()}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url, params=params)
            data = response.json()
            res = data.get("response", {})
            if res:
                await set_to_mem_cache(cache_key, res, ttl_seconds=ttl_seconds)
            return res
    except Exception as e:
        logger.warning(f"[SteamUID] 获取玩家装备项失败 steamid={steamid64}: {e}")
        return {}


async def get_miniprofile(steamid64: str, ttl_seconds: float | None = None) -> dict:
    """获取 Steam miniprofile JSON 数据（等级/徽章/背景/头像，带根据设置 CacheTime 的内存 TTL 缓存）"""
    cache_key = f"miniprofile_{steamid64}"
    cached = await get_from_mem_cache(cache_key)
    if cached is not None:
        return cached

    community_url = SteamConfig.get_config("CommunityBaseURL").data
    steamid32 = int(steamid64) - 76561197960265728
    url = f"{community_url}/miniprofile/{steamid32}/json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params={"l": get_current_lang()})
            res = response.json()
            if res and isinstance(res, dict):
                await set_to_mem_cache(cache_key, res, ttl_seconds=ttl_seconds)
            return res
    except Exception as e:
        logger.warning(f"[SteamUID] 获取 miniprofile 失败 steamid={steamid64}: {e}")
        return {}


async def search_game_store(keyword: str) -> list[dict]:
    """通过 Steam 官方商店搜索接口按游戏名检索候选列表（带本地缓存）"""
    term = keyword.strip()
    if not term:
        return []

    cache_key = f"search_{term.lower()}"
    cached = await SteamApiCache.get_cache(cache_key)
    if cached is not None:
        try:
            return json.loads(cached)
        except Exception:
            pass

    base_url = SteamConfig.get_config("storeBaseURL").data
    url = f"{base_url}{SteamAPI.store_Search}"
    cc = get_current_cc()
    params = {
        "term": term,
        "l": get_current_lang(),
        "cc": cc,
    }
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            return []
        data = response.json()
        items = data.get("items", []) if isinstance(data, dict) else []

    if items:
        await SteamApiCache.upsert_cache(cache_key, json.dumps(items, ensure_ascii=False))
    return items


async def get_game_announcements(
    appid: str,
    lang: str | None = None,
    count: int = 5,
    offset: int = 0,
) -> list[dict]:
    """获取指定游戏的多语言官方公告列表。
    
    请求 store.steampowered.com/events/ajaxgetpartnereventspageable/ 接口，
    Steam 将根据 lang 返回对应语言版本的公告内容（若无对应语言则自动回退）。
    """
    if lang is None:
        lang = get_current_lang()

    base_url = SteamConfig.get_config("storeBaseURL").data
    url = f"{base_url}{SteamAPI.events_GetPartnerEventsPageable}"
    params = {
        "appid": str(appid),
        "clan_accountid": 0,
        "offset": offset,
        "count": count,
        "l": lang,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code != 200:
                logger.warning(
                    f"[SteamUID] 获取游戏公告失败 appid={appid}, status_code={response.status_code}"
                )
                return []
            data = response.json()
    except Exception as e:
        logger.warning(f"[SteamUID] 请求游戏公告接口异常 appid={appid}: {e!r}")
        return []

    events = data.get("events", []) if isinstance(data, dict) else []
    result = []
    for event in events:
        announcement = event.get("announcement_body") or {}
        gid = str(event.get("gid") or announcement.get("gid") or "")
        title = event.get("event_name") or announcement.get("headline") or "无标题公告"
        post_time = int(event.get("rtime32_post_time") or event.get("rtime32_start_time") or 0)
        event_type = int(event.get("event_type") or 28)
        headline = announcement.get("headline") or ""
        body = announcement.get("body") or ""
        
        # 尝试从 jsondata 中获取封面图等
        clan_image = None
        try:
            jsondata_str = event.get("jsondata")
            if jsondata_str:
                jsondata = json.loads(jsondata_str) if isinstance(jsondata_str, str) else jsondata_str
                if isinstance(jsondata, dict):
                    clan_image = jsondata.get("capsule_image")
        except Exception:
            pass

        item = {
            "gid": gid,
            "title": title,
            "post_time": post_time,
            "event_type": event_type,
            "headline": headline,
            "body": body,
            "url": f"https://store.steampowered.com/news/app/{appid}/view/{gid}",
            "clan_image": clan_image,
            "raw_event": event,
        }
        result.append(item)

    return result


async def get_user_wishlist(steamid64: str) -> list[dict]:
    """获取玩家的 Steam 愿望单列表。

    返回 items 列表，每项包含:
        - appid: int
        - priority: int
        - date_added: int (Unix 秒时间戳)
    按 priority 升序排序。
    """
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetWishlist}"
    params = {
        "key": api_key,
        "steamid": steamid64,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(
                    f"[SteamUID] 获取愿望单失败 steamid={steamid64}, status_code={response.status_code}"
                )
                return []
            data = response.json()
            items = data.get("response", {}).get("items", [])
            if isinstance(items, list):
                # 按 priority 升序排序（0 优先级最高）
                items.sort(key=lambda x: (x.get("priority", 0), -x.get("date_added", 0)))
                return items
    except Exception as e:
        logger.warning(f"[SteamUID] 请求愿望单接口异常 steamid={steamid64}: {e!r}")
    return []

