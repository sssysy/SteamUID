"""Steam 订阅推送开关命令的实现。"""

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.helper.bind import (
    is_subscribed,
    subscribe_kind,
    unsubscribe_kind,
    get_main_steamid64,
)
from ..utils.helper.status import NOTIFY_KINDS


async def _current_steamid64(ev: Event) -> str:
    """取当前会话当前账号；未绑定抛校验错误，交由命令边界回执。"""
    steamid64 = await get_main_steamid64(ev, ev.user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")
    return steamid64


async def toggle_subscribe(bot: Bot, ev: Event, kind: str, enable: bool) -> None:
    """开启 / 关闭当前账号某类推送并回执。"""
    steamid64 = await _current_steamid64(ev)
    if enable:
        await subscribe_kind(ev, steamid64, kind)
        await bot.send(f"已订阅 {kind} 推送")
        return
    if not await is_subscribed(ev, steamid64, kind):
        await bot.send(f"该账号未订阅 {kind} 推送")
        return
    await unsubscribe_kind(ev, steamid64, kind)
    await bot.send(f"已取消订阅 {kind} 推送")


async def toggle_all_subscribe(bot: Bot, ev: Event, enable: bool) -> None:
    """全部推送类型的总开关。"""
    steamid64 = await _current_steamid64(ev)
    if enable:
        for kind in NOTIFY_KINDS:
            await subscribe_kind(ev, steamid64, kind)
        await bot.send("已开启全部推送")
        return
    for kind in NOTIFY_KINDS:
        await unsubscribe_kind(ev, steamid64, kind)
    await bot.send("已关闭全部推送")
