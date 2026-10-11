"""Steam 订阅推送命令：按通知类型开关当前账号的个人推送订阅。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .subscribe_services import toggle_subscribe, toggle_all_subscribe
from ..utils.helper.status import NOTIFY_KINDS
from ..utils.helper.command import command_guard

subscribe_sv = SV("Steam订阅推送")

# 键就是整条命令词：类型取自通知词表，整串匹配才不会抢走 steam订阅公告 等命令
_SUBSCRIBE_CMDS: dict[str, str] = {f"订阅{kind}推送": kind for kind in NOTIFY_KINDS}
_UNSUBSCRIBE_CMDS: dict[str, str] = {f"取消订阅{kind}推送": kind for kind in NOTIFY_KINDS}
_ALL_CMDS: dict[str, bool] = {"订阅推送": True, "取消订阅推送": False}


@subscribe_sv.on_fullmatch(tuple(_SUBSCRIBE_CMDS), block=True)
@command_guard
async def steam_subscribe_push(bot: Bot, ev: Event) -> None:
    """steam订阅{类型}推送：为当前账号开启该类推送。"""
    await toggle_subscribe(bot, ev, _SUBSCRIBE_CMDS[ev.command], enable=True)


@subscribe_sv.on_fullmatch(tuple(_UNSUBSCRIBE_CMDS), block=True)
@command_guard
async def steam_unsubscribe_push(bot: Bot, ev: Event) -> None:
    """steam取消订阅{类型}推送：为当前账号关闭该类推送。"""
    await toggle_subscribe(bot, ev, _UNSUBSCRIBE_CMDS[ev.command], enable=False)


@subscribe_sv.on_fullmatch(tuple(_ALL_CMDS), block=True)
@command_guard
async def steam_toggle_all_push(bot: Bot, ev: Event) -> None:
    """steam订阅推送 / steam取消订阅推送：全部推送类型的总开关。"""
    await toggle_all_subscribe(bot, ev, enable=_ALL_CMDS[ev.command])
