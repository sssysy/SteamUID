import random
from io import BytesIO

from gsuid_core.data_store import get_res_path
from gsuid_core.segment import pic_quality

from ..SteamConfig import SteamConfig
from ..SteamConfig.interface import SteamAPI
from ..utils.api import get_steamlibrary_by_steamid64
from ..utils.exceptions import SteamConfigError, SteamValidationError
from ..utils.PIL.draw import draw_what_to_play
from ..utils.PIL.steam_wall import build_wall
from ..utils.utils import batch_download_images


async def build_library_wall(steamid64: str) -> bytes:
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    library = await get_steamlibrary_by_steamid64(api_key, steamid64)
    if library.get("games") is None:
        raise SteamValidationError("获取 steam 游戏库列表失败")

    gameinfo = []
    cdn_urls = []
    played_times = []
    for game in library.get("games", []):
        appid = game.get("appid")
        url = SteamAPI.GetGameCoverImageURL(appid, variant='library_600x900')
        cdn_urls.append(url)
        played_time = (
            game.get("playtime_forever", 0) or
            game.get("playtime_windows_forever", 0) +
            game.get("playtime_mac_forever", 0) +
            game.get("playtime_linux_forever", 0) +
            game.get("playtime_deck_forever", 0)
        )
        played_times.append(played_time)

    cache_path = get_res_path() / 'SteamUID' / 'cache' / 'librarycover'
    cache_path.mkdir(parents=True, exist_ok=True)
    downloaded_paths = await batch_download_images(cdn_urls, str(cache_path))
    for i, url in enumerate(downloaded_paths):
        gameinfo.append((url, played_times[i]))

    if not gameinfo:
        raise SteamValidationError("该 steam 账号暂无游戏库存")

    wall = build_wall(gameinfo)

    buf = BytesIO()
    wall.save(buf, format="JPEG", quality=pic_quality, subsampling=0)
    return buf.getvalue()


async def build_random_pick(steamid64: str) -> bytes:
    """从用户 Steam 游戏库中随机选取 3 款游戏，生成推荐图片。"""
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    library = await get_steamlibrary_by_steamid64(api_key, steamid64)
    games = library.get("games")
    if games is None:
        raise SteamValidationError("获取 steam 游戏库列表失败")
    if not games:
        raise SteamValidationError("该 steam 账号暂无游戏库存")
    pick_count = min(3, len(games))
    picks = random.sample(games, pick_count)
    game_data = []

    for game in picks:
        appid = str(game.get("appid", ""))
        name = game.get("name", "未知游戏")
        playtime = (
            game.get("playtime_forever", 0) or
            game.get("playtime_windows_forever", 0) +
            game.get("playtime_mac_forever", 0) +
            game.get("playtime_linux_forever", 0) +
            game.get("playtime_deck_forever", 0)
        )
        cover_url = SteamAPI.GetGameCoverImageURL(appid, variant='library_600x900')
        game_data.append({
            "appid": appid,
            "name": name,
            "playtime": playtime,
            "cover_url": cover_url,
        })

    img = await draw_what_to_play(game_data)
    img = img.convert("RGB")

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=pic_quality, subsampling=0)
    return buf.getvalue()
