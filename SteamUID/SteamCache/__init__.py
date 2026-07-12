from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.database.models_cache import SteamApiCache, SteamArchivementCache

sv_steam_cache = SV('steam缓存')


@sv_steam_cache.on_command(('清除全部缓存', '删除全部缓存'))
async def clear_all_cache(bot: Bot, ev: Event):
    api_count = await SteamApiCache.delete_all()
    ach_count = await SteamArchivementCache.delete_all()
    await bot.send(
        f'[SteamUID] 已清除全部缓存！\n'
        f'接口缓存: {api_count} 条\n'
        f'成就缓存: {ach_count} 条'
    )
