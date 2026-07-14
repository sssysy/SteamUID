from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .cache_service import purge_all, purge_file_cache, purge_db_cache

sv_steam_cache = SV('steam清除缓存')


@sv_steam_cache.on_command(('清除全部缓存', '删除全部缓存'))
async def clear_all_cache(bot: Bot, ev: Event):
    api_count, ach_count, file_count = await purge_all()
    await bot.send(
        f'[SteamUID] 已清除全部缓存！\n'
        f'接口缓存: {api_count} 条\n'
        f'成就缓存: {ach_count} 条\n'
        f'缓存文件: {file_count} 个'
    )

@sv_steam_cache.on_command(('清除本地缓存', '删除本地缓存'))
async def clear_local_cache(bot: Bot, ev: Event):
    file_count = await purge_file_cache()
    await bot.send(
        f'[SteamUID] 已清除本地缓存！\n'
        f'缓存文件: {file_count} 个'
    )

@sv_steam_cache.on_command(('清除数据库缓存', '删除数据库缓存'))
async def clear_db_cache(bot: Bot, ev: Event):
    api_count, ach_count = await purge_db_cache()
    await bot.send(
        f'[SteamUID] 已清除数据库缓存！\n'
        f'接口缓存: {api_count} 条\n'
        f'成就缓存: {ach_count} 条'
    )