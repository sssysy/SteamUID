import httpx
from ..SteamConfig.interface import SteamAPI
from ..SteamConfig import SteamConfig


async def get_user_Summaries(steamid64: str | list[str]) -> list:
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    if isinstance(steamid64, list):
        steamid64 = ','.join(steamid64)

    url = f"{base_url}{SteamAPI.api_GetPlayerSummaries}"
    params = {
        "key": api_key,
        "steamids": steamid64,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        players = data.get("response", {}).get("players", [])
        return players
    
async def get_game_info(appid: str) -> dict:
    base_url = SteamConfig.get_config("storeBaseURL").data
    url = f"{base_url}{SteamAPI.store_GetGameDetails}"
    params = {
        "appids": appid,
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data.get(appid, {})
    
async def get_steamlibrary_by_steamid64(api_key: str, steamid64: str) -> dict:
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetOwnedGames}"
    params = {
        "key": api_key,
        "steamid": steamid64,
        "include_appinfo": True,
        "include_played_free_games": True,
    }
    async with httpx.AsyncClient() as client:
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
        "l": "zh-CN",
    }    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data.get("playerstats", {})
    
async def get_archivement_img(appid: str, archivement_name: str) -> str:
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetSchemaForGame}"
    params = {
        "key": api_key,
        "appid": appid,
        "l": "zh-CN",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        archivements =  data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
        for archivement in archivements:
            if archivement.get("name") == archivement_name:
                return archivement.get("icon", "")
        return ""

async def get_archivement_schema(appid: str) -> list[dict]:
    """一次性获取游戏成就 Schema（含 icon/icongray/displayName/description）。

    返回 game.availableGameStats.achievements 列表；无数据时返回空列表。
    供「游戏成就」命令批量匹配图标使用，不影响 get_archivement_img。
    """
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    base_url = SteamConfig.get_config("APIBaseURL").data
    url = f"{base_url}{SteamAPI.api_GetSchemaForGame}"
    params = {
        "key": api_key,
        "appid": appid,
        "l": "zh-CN",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        return data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
