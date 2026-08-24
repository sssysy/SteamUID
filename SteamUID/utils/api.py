import json
import asyncio
import time
import httpx
from gsuid_core.logger import logger
from ..SteamConfig.interface import SteamAPI
from ..SteamConfig import SteamConfig
from .database.models_cache import SteamApiCache, SteamArchivementCache
from .exceptions import SteamValidationError

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
        f"user_summary_{steamid64}",
        f"profile_items_{steamid64}",
        f"miniprofile_{steamid64}",
    ]
    async with _CACHE_LOCK:
        for k in keys_to_delete:
            _MEM_CACHE.pop(k, None)


async def get_user_Summaries(steamid64: str | list[str], ttl_seconds: float | None = None) -> list:
    """获取玩家摘要数据（支持单 ID 或列表，带根据设置 CacheTime 的内存 TTL 缓存）"""
    if ttl_seconds is None:
        ttl_seconds = get_default_cache_ttl()

    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    if isinstance(steamid64, str):
        steamids = [steamid64]
    else:
        steamids = list(steamid64)

    all_players: list[dict] = []
    uncached_ids: list[str] = []

    # 1. 尝试从缓存中命中
    for sid in steamids:
        cached = await get_from_mem_cache(f"user_summary_{sid}")
        if cached is not None:
            all_players.append(cached)
        else:
            uncached_ids.append(sid)

    if not uncached_ids:
        return all_players

    # 2. 分批请求未缓存的 Steam ID
    url = f"{base_url}{SteamAPI.api_GetPlayerSummaries}"
    batches = [uncached_ids[i:i + 50] for i in range(0, len(uncached_ids), 50)]

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

    # 3. 写入缓存并合并
    for players in results:
        for p in players:
            sid = p.get("steamid")
            if sid:
                await set_to_mem_cache(f"user_summary_{sid}", p, ttl_seconds=ttl_seconds)
            all_players.append(p)

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


async def get_profile_items_equipped(steamid64: str, ttl_seconds: float | None = None) -> dict:
    """获取玩家装备项（头像框/动画头像/迷你资料背景，带根据设置 CacheTime 的内存 TTL 缓存）"""
    cache_key = f"profile_items_{steamid64}"
    cached = await get_from_mem_cache(cache_key)
    if cached is not None:
        return cached

    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetProfileItemsEquipped}"
    params = {"key": api_key, "steamid": steamid64, "l": "schinese"}
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
            response = await client.get(url, params={"l": "schinese"})
            res = response.json()
            if res and isinstance(res, dict):
                await set_to_mem_cache(cache_key, res, ttl_seconds=ttl_seconds)
            return res
    except Exception as e:
        logger.warning(f"[SteamUID] 获取 miniprofile 失败 steamid={steamid64}: {e}")
        return {}


async def refresh_user_cache(steamids: list[str]) -> int:
    """清除并强制重新请求指定的 steamid64 用户信息缓存（支持批量）"""
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


async def get_user_pill_data(steamid64: str) -> dict:
    """并发查询并聚合构建「药丸型卡片」所需的用户数据字典（全走三路 TTL 缓存）"""
    from .utils import steamid64_to_friend_code

    players_res, miniprofile_data, items_data = await asyncio.gather(
        get_user_Summaries(steamid64),
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        return_exceptions=True,
    )

    player = players_res[0] if (isinstance(players_res, list) and players_res) else {}
    user_name = player.get("personaname", "未知用户")
    friend_code = steamid64_to_friend_code(steamid64)

    avatar_url = player.get("avatarfull", "")
    if isinstance(miniprofile_data, dict) and miniprofile_data.get("avatar_url"):
        avatar_url = miniprofile_data["avatar_url"]

    avatar_frame_url = None
    if isinstance(items_data, dict):
        frame = items_data.get("avatar_frame", {})
        if frame.get("image_small"):
            avatar_frame_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{frame['image_small']}"
    if not avatar_frame_url and isinstance(miniprofile_data, dict):
        avatar_frame_url = miniprofile_data.get("avatar_frame")

    bg_url = None
    if isinstance(items_data, dict):
        mini_bg = items_data.get("mini_profile_background", {})
        if mini_bg.get("image_large"):
            bg_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{mini_bg['image_large']}"
    if not bg_url and isinstance(miniprofile_data, dict):
        bg = miniprofile_data.get("profile_background", {})
        bg_url = bg.get("image")

    return {
        "name": user_name,
        "friend_code": friend_code,
        "avatar_url": avatar_url,
        "avatar_frame_url": avatar_frame_url,
        "bg_url": bg_url,
    }


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


async def get_user_year_in_review_share_images(
    steamid64: str, year: int, language: str = "schinese"
) -> list[str]:
    """获取指定 steamid64 在指定年份的年度回顾分享图片 URL 列表。

    优先调用官方 Web API（ISaleFeatureService/GetUserYearInReviewShareImage/v1），
    该接口会返回包括 1080x1080、1080x1920、1200x628 等在内的预生成分享图片。
    若 API 请求失败或为空，回退到 Steam 商店页面解析 OpenGraph 元数据。
    若用户未公开或无数据，返回空列表。
    """
    import re

    base_cdn = "https://shared.fastly.steamstatic.com/social_sharing/"
    image_urls: list[str] = []

    # 1. 优先调用官方 Web API
    api_cfg = SteamConfig.get_config("APIBaseURL").data
    api_base_url = (
        api_cfg
        if isinstance(api_cfg, str) and api_cfg.strip()
        else "https://api.steampowered.com"
    ).rstrip("/")
    api_url = f"{api_base_url}{SteamAPI.api_GetUserYearInReviewShareImage}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://store.steampowered.com",
        "Referer": f"https://store.steampowered.com/replay/{steamid64}/{year}",
    }

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                api_url,
                params={"steamid": steamid64, "year": year, "language": language},
                headers=headers,
            )
            if resp.status_code == 200 and resp.text:
                data = resp.json()
                images = data.get("response", {}).get("images", [])
                for img in images:
                    url_path = img.get("url_path")
                    if url_path:
                        full_url = f"{base_cdn}{url_path.lstrip('/')}"
                        if full_url not in image_urls:
                            image_urls.append(full_url)
    except Exception as e:
        logger.warning(
            f"[SteamUID] WebAPI 获取年度回顾分享图异常 steamid={steamid64} year={year}: {e}"
        )

    if image_urls:
        return image_urls

    # 2. 回退：通过 Steam 商店年度回顾页面解析 OpenGraph 分享图
    store_cfg = SteamConfig.get_config("storeBaseURL").data
    store_base_url = (
        store_cfg
        if isinstance(store_cfg, str) and store_cfg.strip()
        else "https://store.steampowered.com"
    ).rstrip("/")
    store_url = f"{store_base_url}/replay/{steamid64}/{year}"

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(store_url, headers=headers)
            if resp.status_code == 200 and resp.text:
                og_matches = re.findall(
                    r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
                    resp.text,
                    re.IGNORECASE,
                )
                if not og_matches:
                    og_matches = re.findall(
                        r'<link\s+rel=["\']image_src["\']\s+href=["\']([^"\']+)["\']',
                        resp.text,
                        re.IGNORECASE,
                    )

                for img in og_matches:
                    img = img.strip()
                    # 排除未公开时的通用占位图
                    if (
                        "social_share_image_generic" in img
                        or "/public/images/yearinreview/" in img
                    ):
                        continue
                    if "social_sharing/replay" in img or "/social_sharing/" in img:
                        if img not in image_urls:
                            image_urls.append(img)
    except Exception as e:
        logger.warning(
            f"[SteamUID] 商店页解析年度回顾分享图异常 steamid={steamid64} year={year}: {e}"
        )

    return image_urls




