"""Steam 订阅推送命令：按通知类型开关当前会话的推送订阅与订阅状态查询。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .subscribe_services import toggle_subscribe, toggle_all_subscribe, build_subscribe_status_text
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


@subscribe_sv.on_fullmatch(
    "订阅状态",
    block=True,
    to_ai="""查询当前群聊或私聊会话的 Steam 推送订阅状态。
当用户询问自己订阅了哪些 Steam 推送、公告订阅数量或降价订阅数量时调用。
无需参数，自动读取当前会话。

Args:
    text: 无需参数，留空即可。
""",
    covers=["当前会话 Steam 推送订阅状态、公告订阅数、降价订阅数"],
    aliases=["Steam·推送订阅状态", "Steam·订阅查询"],
)
@command_guard
async def steam_subscribe_status(bot: Bot, ev: Event) -> None:
    """steam订阅状态：查看本会话的推送开关与公告 / 降价订阅数量。"""
    await bot.send(await build_subscribe_status_text(ev))
