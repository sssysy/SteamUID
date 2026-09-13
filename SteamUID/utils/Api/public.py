"""公开 WebAPI / 商店接口"""
import asyncio
import json

import httpx
from gsuid_core.logger import logger

from ...SteamConfig import SteamConfig, get_current_cc, get_current_lang
from ..database.models_cache import SteamApiCache, SteamArchivementCache
from ..exceptions import TIMEOUT_ERR_MSG, SteamTimeoutError
from ..helpers.api_fallback import fetch_with_user_token
from .client import make_async_client
from .endpoints import SteamAPI
from .cover import get_game_cover_url, get_official_cover_url

# Steam 商店年龄与成年内容验证静态 Cookie
STEAM_STORE_COOKIES = {
    "birthtime": "786297601",
    "lastagecheckage": "1-0-1995",
    "wants_mature_content": "1",
}


def get_default_cache_ttl() -> float:
    """根据 SteamConfig 中的 CacheTime (天) 转换为缓存秒数"""
    return float(SteamConfig.get_config("CacheTime").data) * 86400


async def get_user_Summaries(steamid64: str | list[str]) -> list:
    """获取玩家摘要数据（即时请求不使用缓存）"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    if isinstance(steamid64, str):
        steamids = [steamid64]
    else:
        steamids = list(steamid64)

    if not steamids:
        return []

    url = f"{base_url}{SteamAPI.api_GetPlayerSummaries}"
    batches = [steamids[i : i + 50] for i in range(0, len(steamids), 50)]

    timeout_count = 0

    async def fetch_batch(client: httpx.AsyncClient, batch: list[str]) -> list:
        nonlocal timeout_count
        try:
            params = {"key": api_key, "steamids": ",".join(batch)}
            response = await client.get(url, params=params)
            data = response.json()
            return data.get("response", {}).get("players", [])
        except (httpx.TimeoutException, asyncio.TimeoutError) as e:
            logger.warning(f"[SteamUID] 获取玩家摘要超时 batch={batch[:3]}: {e}")
            timeout_count += 1
            return []
        except Exception as e:
            logger.warning(f"[SteamUID] 获取玩家摘要失败 batch={batch[:3]}: {e}")
            return []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            tasks = [fetch_batch(client, batch) for batch in batches]
            results = await asyncio.gather(*tasks)
    except (httpx.TimeoutException, asyncio.TimeoutError):
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)

    if timeout_count > 0 and timeout_count == len(batches):
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)

    all_players: list[dict] = []
    for players in results:
        all_players.extend(players)

    return all_players


async def get_game_info(appid: str) -> dict:
    """获取游戏详情（带缓存：命中有效缓存则不请求API）"""
    cached = await SteamApiCache.get_cache(appid)
    if cached is not None:
        try:
            parsed = json.loads(cached)
            if isinstance(parsed, dict) and parsed.get("success"):
                return parsed
            await SteamApiCache.delete_cache(appid)
        except Exception:
            await SteamApiCache.delete_cache(appid)

    base_url = SteamConfig.get_config("storeBaseURL").data
    url = f"{base_url}{SteamAPI.store_GetGameDetails}"
    params = {
        "appids": appid,
        "cc": get_current_cc(),
        "l": get_current_lang(),
    }
    result = {}
    try:
        async with httpx.AsyncClient(timeout=10, cookies=STEAM_STORE_COOKIES) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                result = data.get(appid, {}) if isinstance(data, dict) else {}
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.warning(f"[SteamUID] 获取游戏详情超时 appid={appid}: {e}")
    except Exception as e:
        logger.warning(f"[SteamUID] 获取游戏详情异常 appid={appid}: {e}")

    # 1. 锁区探测：若指定地区返回失败且设置了国家/地区，尝试无区域限制重新探测一次
    if not (isinstance(result, dict) and result.get("success")):
        current_cc = get_current_cc()
        if current_cc:
            try:
                global_params = {
                    "appids": appid,
                    "l": get_current_lang(),
                }
                async with httpx.AsyncClient(timeout=8, cookies=STEAM_STORE_COOKIES) as client:
                    resp_global = await client.get(url, params=global_params)
                    if resp_global.status_code == 200:
                        data_global = resp_global.json()
                        result_global = data_global.get(appid, {}) if isinstance(data_global, dict) else {}
                        if isinstance(result_global, dict) and result_global.get("success"):
                            result = result_global
            except Exception:
                pass

    if isinstance(result, dict) and result.get("success"):
        # 统一规范化与解析封面
        data_obj = result.get("data", {})
        if isinstance(data_obj, dict):
            raw_header = data_obj.get("header_image")
            cover_url = await get_game_cover_url(appid, header_image=raw_header)
            data_obj["header_image"] = cover_url
        await SteamApiCache.upsert_cache(appid, json.dumps(result, ensure_ascii=False))
        return result

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
    return get_official_cover_url(appid, "capsule_sm_120")


async def get_steamlibrary_by_steamid64(api_key: str, steamid64: str) -> dict:
    """取玩家游戏库（支持优先使用登录凭据获取私密库存，失效自动降级）"""
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetOwnedGames}"

    # 1. 若开启允许私密数据，优先尝试使用用户的 access_token
    body = await fetch_with_user_token(
        steamid64,
        url,
        {
            "steamid": steamid64,
            "include_appinfo": True,
            "include_played_free_games": True,
            "include_extended_appinfo": True,
        },
        tag="玩家游戏库",
    )
    if body is not None:
        games = (body.get("response") or {}).get("games")
        if games is not None:
            return body.get("response", {})

    # 2. 降级使用公共 api_key 查询公开库
    params = {
        "key": api_key,
        "steamid": steamid64,
        "include_appinfo": True,
        "include_played_free_games": True,
    }
    try:
        async with make_async_client(timeout=10) as client:
            response = await client.get(url, params=params)
            data = response.json()
            return data.get("response", {})
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(f"[SteamUID] 获取玩家游戏库超时 steamid={steamid64}")
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)
    except Exception as e:
        logger.warning(f"[SteamUID] 获取玩家游戏库异常 steamid={steamid64}: {e}")
        return {}


async def get_archivement_info(appid: str, steamid64: str):
    """获取玩家指定游戏的成就信息（优先使用用户凭证获取私密成就）"""
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetPlayerAchievements}"
    current_lang = get_current_lang()

    # 1. 若开启允许私密数据，优先尝试使用用户的 access_token
    body = await fetch_with_user_token(
        steamid64,
        url,
        {"appid": appid, "steamid": steamid64, "l": current_lang},
        tag="玩家成就",
    )
    if body is not None:
        playerstats = body.get("playerstats", {})
        if playerstats.get("achievements") is not None:
            return playerstats

    # 2. 降级使用公共 key 查询
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    params = {
        "key": api_key,
        "appid": appid,
        "steamid": steamid64,
        "l": current_lang,
    }
    try:
        async with make_async_client(timeout=10) as client:
            response = await client.get(url, params=params)
            data = response.json()
            return data.get("playerstats", {})
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(
            f"[SteamUID] 获取玩家成就超时 appid={appid} steamid={steamid64}"
        )
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)
    except Exception as e:
        logger.warning(
            f"[SteamUID] 获取玩家成就异常 appid={appid} steamid={steamid64}: {e}"
        )
        return {}


async def get_archivement_img(appid: str, archivement_name: str) -> str:
    """获取单个成就的icon URL（复用 get_archivement_schema 缓存，不单独请求API）"""
    schema_list = await get_archivement_schema(appid)
    for archivement in schema_list:
        if archivement.get("name") == archivement_name:
            return archivement.get("icon", "")
    return ""


async def get_archivement_schema(appid: str) -> list[dict]:
    """一次性获取游戏成就 Schema（含 icon/icongray/displayName/description）。"""
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
    achievements = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            data = response.json()
            achievements = (
                data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
            )
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(f"[SteamUID] 获取成就 Schema 超时 appid={appid}")
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)
    except Exception as e:
        logger.warning(f"[SteamUID] 获取成就 Schema 异常 appid={appid}: {e}")
        achievements = []

    if achievements:
        await SteamArchivementCache.upsert_cache(
            appid, json.dumps(achievements, ensure_ascii=False)
        )
    return achievements


async def get_price_data(appid: str | list[str]) -> dict:
    """获取游戏价格数据（支持单 AppID 或列表批量查询）"""
    base_url = SteamConfig.get_config("storeBaseURL").data
    cc = get_current_cc()

    if isinstance(appid, str):
        appid = [appid]

    url = f"{base_url}{SteamAPI.store_GetGameDetails}"
    batches = [appid[i : i + 50] for i in range(0, len(appid), 50)]
    timeout_count = 0

    async def fetch_batch(client: httpx.AsyncClient, batch: list[str]) -> dict:
        nonlocal timeout_count
        try:
            params = {
                "appids": ",".join(batch),
                "cc": cc,
                "filters": "price_overview",
            }
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    return data
        except (httpx.TimeoutException, asyncio.TimeoutError) as e:
            logger.warning(
                f"[SteamUID] 批量获取游戏价格超时 batch={batch[:3]}...: {e}"
            )
            timeout_count += 1
        except Exception as e:
            logger.warning(
                f"[SteamUID] 批量获取游戏价格异常 batch={batch[:3]}...: {e}"
            )
        return {}

    try:
        async with httpx.AsyncClient(
            timeout=15, cookies=STEAM_STORE_COOKIES
        ) as client:
            tasks = [fetch_batch(client, batch) for batch in batches]
            results = await asyncio.gather(*tasks, return_exceptions=True)
    except (httpx.TimeoutException, asyncio.TimeoutError):
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)

    if timeout_count > 0 and timeout_count == len(batches):
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)

    all_prices: dict = {}
    for res in results:
        if isinstance(res, dict):
            all_prices.update(res)
    return all_prices


async def get_profile_items_equipped(steamid64: str) -> dict:
    """获取玩家装备项（头像框/动画头像/迷你资料背景，即时请求不用内存缓存）"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetProfileItemsEquipped}"
    params = {"key": api_key, "steamid": steamid64, "l": get_current_lang()}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, params=params)
            data = response.json()
            res = data.get("response", {})
            return res
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.warning(f"[SteamUID] 获取玩家装备项超时 steamid={steamid64}: {e}")
        return {}
    except Exception as e:
        logger.warning(f"[SteamUID] 获取玩家装备项失败 steamid={steamid64}: {e}")
        return {}


async def get_miniprofile(steamid64: str) -> dict:
    """获取 Steam miniprofile JSON 数据（等级/徽章/背景/头像，即时请求不用内存缓存）"""
    community_url = SteamConfig.get_config("CommunityBaseURL").data
    steamid32 = int(steamid64) - 76561197960265728
    url = f"{community_url}/miniprofile/{steamid32}/json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params={"l": get_current_lang()})
            res = response.json()
            return res
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.warning(f"[SteamUID] 获取 miniprofile 超时 steamid={steamid64}: {e}")
        return {}
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
    current_cc = get_current_cc()
    params = {
        "term": term,
        "l": get_current_lang(),
        "cc": current_cc,
    }
    items = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", []) if isinstance(data, dict) else []

            # 某个地区如果没结果再回退全球区 (US)
            if not items and current_cc != "US":
                params_global = {
                    "term": term,
                    "l": get_current_lang(),
                    "cc": "US",
                }
                resp_global = await client.get(url, params=params_global)
                if resp_global.status_code == 200:
                    data_global = resp_global.json()
                    items = data_global.get("items", []) if isinstance(data_global, dict) else []
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(f"[SteamUID] 搜索游戏超时 keyword={keyword}")
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)
    except Exception as e:
        logger.warning(f"[SteamUID] 搜索游戏异常 keyword={keyword}: {e}")
        return []

    if items:
        await SteamApiCache.upsert_cache(cache_key, json.dumps(items, ensure_ascii=False))
    return items


async def get_game_announcements(
    appid: str,
    lang: str | None = None,
    count: int = 5,
    offset: int = 0,
) -> list[dict]:
    """获取指定游戏的多语言官方公告列表。"""
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
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(f"[SteamUID] 请求游戏公告接口超时 appid={appid}")
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)
    except Exception as e:
        logger.warning(f"[SteamUID] 请求游戏公告接口异常 appid={appid}: {e!r}")
        return []

    events = data.get("events", []) if isinstance(data, dict) else []
    result = []
    for event in events:
        announcement = event.get("announcement_body") or {}
        gid = str(event.get("gid") or announcement.get("gid") or "")
        title = event.get("event_name") or announcement.get("headline") or "无标题公告"
        post_time = int(
            event.get("rtime32_post_time") or event.get("rtime32_start_time") or 0
        )
        event_type = int(event.get("event_type") or 28)
        headline = announcement.get("headline") or ""
        body = announcement.get("body") or ""

        clan_image = None
        try:
            jsondata_str = event.get("jsondata")
            if jsondata_str:
                jsondata = (
                    json.loads(jsondata_str)
                    if isinstance(jsondata_str, str)
                    else jsondata_str
                )
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
    """获取玩家的 Steam 愿望单列表（优先使用用户凭证获取私密愿望单，按 priority 升序）。"""
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetWishlist}"

    # 1. 若开启允许私密数据，优先尝试使用用户的 access_token
    body = await fetch_with_user_token(
        steamid64, url, {"steamid": steamid64}, tag="愿望单"
    )
    if body is not None:
        items = (body.get("response") or {}).get("items", [])
        if isinstance(items, list) and items:
            items.sort(key=lambda x: (x.get("priority", 0), -x.get("date_added", 0)))
            return items

    # 2. 降级使用公共 API Key 查询
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    params = {
        "key": api_key,
        "steamid": steamid64,
    }
    try:
        async with make_async_client(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(
                    f"[SteamUID] 获取愿望单失败 steamid={steamid64}, status_code={response.status_code}"
                )
                return []
            data = response.json()
            items = data.get("response", {}).get("items", [])
            if isinstance(items, list):
                items.sort(key=lambda x: (x.get("priority", 0), -x.get("date_added", 0)))
                return items
    except (httpx.TimeoutException, asyncio.TimeoutError):
        logger.warning(f"[SteamUID] 请求愿望单接口超时 steamid={steamid64}")
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)
    except Exception as e:
        logger.warning(f"[SteamUID] 请求愿望单接口异常 steamid={steamid64}: {e!r}")
    return []
