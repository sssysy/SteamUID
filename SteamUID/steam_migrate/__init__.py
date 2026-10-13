"""Steam 订阅迁移命令：把 1.0 遗留库内的订阅状态迁移到框架订阅。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .migrate_services import migrate_subscribe_state
from ..utils.helper.command import command_guard

migrate_sv = SV("Steam订阅迁移", pm=1)


@migrate_sv.on_fullmatch("迁移订阅状态", block=True)
@command_guard
async def steam_migrate_subscribe(bot: Bot, ev: Event) -> None:
    """steam迁移订阅状态：把 1.0 库内的订阅开关与任务名迁移到框架订阅。"""
    await migrate_subscribe_state(bot)
