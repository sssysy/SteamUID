"""Steam 缓存立即清除命令的实现。"""

from gsuid_core.bot import Bot

from ..utils.database.model_cache import SteamCache
from ..utils.downloader import clear_cache_files


async def clear_cache(bot: Bot, target: str) -> None:
    """按目标清空缓存并回执：接口=数据库缓存，图片=img_cache，文件=cache。"""
    if target == "接口":
        rows = await SteamCache.clear_all()
        await bot.send(f"已清除接口缓存 {rows} 条")
        return
    if target == "图片":
        images = await clear_cache_files("image")
        await bot.send(f"已清除图片缓存 {images} 个")
        return
    if target == "文件":
        files = await clear_cache_files("file")
        await bot.send(f"已清除文件缓存 {files} 个")
        return
    if target == "全部":
        rows = await SteamCache.clear_all()
        images = await clear_cache_files("image")
        files = await clear_cache_files("file")
        await bot.send(f"已清除全部缓存：接口 {rows} 条、图片 {images} 个、文件 {files} 个")
        return
    raise ValueError(f"不支持的缓存类型: {target}")
