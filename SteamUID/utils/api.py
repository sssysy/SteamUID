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