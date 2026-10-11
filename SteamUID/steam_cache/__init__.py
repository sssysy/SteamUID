"""Steam 缓存管理：清除命令注册与定时清理任务注册。"""

import time

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..steam_config import get_cache_clean_days
from .cache_services import clear_cache
from ..utils.downloader import clean_cache_files
from ..utils.helper.command import command_guard
from ..utils.database.model_cache import SteamCache

_TAG = "[Steam·缓存清理]"

# 整串匹配，避免吃掉 清除XX缓存 之外的普通文本
_CLEAR_PATTERN = r"^(?P<action>清除|删除)(?P<target>全部|接口|图片|文件)缓存$"

cache_sv = SV("Steam缓存管理", pm=1)


@cache_sv.on_regex(_CLEAR_PATTERN, block=True)
@command_guard
async def steam_clear_cache(bot: Bot, ev: Event) -> None:
    """steam清除{全部|接口|图片|文件}缓存 / steam删除...：立即清空对应缓存。"""
    await clear_cache(bot, ev.regex_dict["target"])


_CLEAN_DAYS = get_cache_clean_days()

# 0 表示不清理，且 interval 的 days 不能为 0，直接不注册任务
if _CLEAN_DAYS > 0:

    @scheduler.scheduled_job("interval", days=_CLEAN_DAYS)
    async def clean_steam_cache_job() -> None:
        cutoff = int(time.time()) - _CLEAN_DAYS * 86400
        deleted = await SteamCache.delete_expired(cutoff)
        removed = await clean_cache_files(cutoff)
        logger.info(f"{_TAG} 清理 {_CLEAN_DAYS} 天前的缓存，删除 {deleted} 行 / {removed} 个文件")
