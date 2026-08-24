import json
import asyncio
import httpx
from gsuid_core.logger import logger
from ..SteamConfig.interface import SteamAPI
from ..SteamConfig import SteamConfig
from .database.models_cache import SteamApiCache, SteamArchivementCache
from .exceptions import SteamValidationError



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


async def get_user_static_avatar_frame(steamid64: str) -> str | None:
    """获取用户的静态 Steam 头像框 URL（优先 GetProfileItemsEquipped 静态小图，回退 miniprofile）"""
    try:
        items_data = await get_profile_items_equipped(steamid64)
        if isinstance(items_data, dict):
            frame = items_data.get("avatar_frame", {})
            if frame.get("image_small"):
                return f"https://shared.fastly.steamstatic.com/community_assets/images/{frame['image_small']}"
    except Exception as e:
        logger.debug(f"[SteamUID] 获取装备头像框异常 steamid={steamid64}: {e}")

    try:
        miniprofile_data = await get_miniprofile(steamid64)
        if isinstance(miniprofile_data, dict):
            frame_url = miniprofile_data.get("avatar_frame")
            if frame_url:
                return frame_url
    except Exception as e:
        logger.debug(f"[SteamUID] 获取miniprofile头像框异常 steamid={steamid64}: {e}")

    return None


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
    cc = SteamConfig.get_config("pricecc").data or "cn"
    params = {
        "term": term,
        "l": "schinese",
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


async def resolve_game_input(input_text: str) -> tuple[str, str, bool]:
    """解析用户输入的游戏标识（纯数字 AppID 或 游戏名称）。

    返回: (appid, game_name, is_from_search)
    - 若输入为纯数字 AppID: 返回 (appid, appid 或 从详情/缓存获取的游戏名, False)
    - 若输入为游戏名且搜索成功: 返回 (appid, 匹配到的游戏名, True)
    - 若未找到匹配游戏: 抛出 SteamValidationError
    """
    raw_input = input_text.strip()
    if not raw_input:
        raise SteamValidationError("请输入游戏名或 AppID！")

    # 1. 如果是纯数字，直接作为 AppID 处理
    if raw_input.isdigit():
        appid = raw_input
        # 尝试从缓存或详情中获取游戏名称以方便后续使用
        game_name = appid
        cached = await SteamApiCache.get_cache(appid)
        if cached:
            try:
                c_data = json.loads(cached)
                name = c_data.get("data", {}).get("name") if isinstance(c_data, dict) else None
                if name:
                    game_name = name
            except Exception:
                pass
        return appid, game_name, False

    # 2. 如果是非纯数字，调用官方商店搜索接口
    items = await search_game_store(raw_input)
    if not items:
        raise SteamValidationError(f"未找到与【{raw_input}】相关的游戏，请检查游戏名称或直接输入 AppID")

    # 优先选取 type == 'app'（本体游戏），避免优先匹配到 package/sub/bundle
    target_item = None
    for item in items:
        if item.get("type") == "app" and item.get("id") and item.get("name"):
            target_item = item
            break
    if target_item is None:
        target_item = items[0]

    matched_appid = str(target_item.get("id"))
    matched_name = str(target_item.get("name") or raw_input)
    return matched_appid, matched_name, True


async def get_user_year_in_review_share_images(steamid64: str, year: int) -> list[str]:
    """获取指定 steamid64 在指定年份的年度回顾分享图片 URL 列表。

    调用 ISaleFeatureService/GetUserYearInReviewShareImage/v1 接口。
    若未公开或无数据，返回空列表。
    """
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetUserYearInReviewShareImage}"
    params = {
        "key": api_key,
        "steamid": steamid64,
        "year": year,
    }
    image_urls: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                images = data.get("response", {}).get("images", [])
                for img in images:
                    if isinstance(img, dict) and img.get("url_path"):
                        url_path = img["url_path"].strip()
                        if url_path.startswith("http://") or url_path.startswith("https://"):
                            image_urls.append(url_path)
                        else:
                            image_urls.append(f"https://shared.akamai.steamstatic.com/social_sharing/{url_path}")
    except Exception as e:
        logger.warning(f"[SteamUID] 获取年度回顾分享图异常 steamid={steamid64} year={year}: {e}")

    return image_urls



