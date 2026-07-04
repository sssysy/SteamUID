from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from ..SteamConfig import SteamConfig
from ..SteamConfig.interface import SteamAPI
from ..utils.database.models import SteamBind
from ..utils.PIL.steam_wall import build_wall
from ..utils.api import get_steamlibrary_by_steamid64
from ..utils.utils import batch_download_images, auto2steamid64
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment

library_SV = SV("steam库存相关")

@library_SV.on_command(("游戏墙", "游戏库"))
async def get_steamlibrary_image(bot: Bot, ev: Event):
    text = ev.text.strip()
    steamid64 = auto2steamid64(text)
    
    # 读取主 steamid64
    if not steamid64: # 没有传入steamid64
        steamid64 = await SteamBind.get_main_id(ev.bot_id,ev.user_id,ev.user_type,ev.group_id)
    # 没有主 ID
    if not steamid64:
        return await bot.send("请先绑定 steam 账号")
    # 没有配置 api_key
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        return await bot.send("请先配置 steam web api key")
    
    # 获取steam库存列表
    try:
        library = await get_steamlibrary_by_steamid64(api_key, steamid64)
        if library.get("games") is None:
            return await bot.send("获取 steam 游戏库列表失败")
    except Exception as e:
        return await bot.send(f"获取 steam 库存失败: {e}")
    await bot.send("正在开始制作封面墙......")

    # 提取 appid 和游戏时长
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

    # 下载图片
    cache_path = get_res_path() / 'SteamUID' / 'cache' / 'librarycover'
    cache_path.mkdir(parents=True, exist_ok=True)
    downloaded_paths = await batch_download_images(cdn_urls, str(cache_path))
    for i, url in enumerate(downloaded_paths):
        gameinfo.append((url, played_times[i]))
    
    if not gameinfo:
        return await bot.send("该 steam 账号暂无游戏库存")
    # 制作封面
    wall = build_wall(gameinfo)
    await bot.send(MessageSegment.image(wall))
