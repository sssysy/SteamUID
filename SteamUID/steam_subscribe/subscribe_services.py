"""Steam 订阅推送开关与订阅状态查询的实现。"""

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..steam_config import SteamConfig
from ..utils.helper.bind import (
    scope_name,
    is_subscribed,
    subscribe_kind,
    scope_task_rows,
    unsubscribe_kind,
    get_main_steamid64,
)
from ..utils.helper.status import NOTIFY_KINDS
from ..utils.helper.announce import SUBSCRIBE_TASK as ANNOUNCE_TASK
from ..utils.helper.price_drop import SUBSCRIBE_TASK as PRICE_TASK

_PREFIX = "[Steam]"


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
        await bot.send(f"已为{scope_name(ev)}订阅 {kind} 推送")
        return
    if not await is_subscribed(ev, steamid64, kind):
        await bot.send(f"{scope_name(ev)}未订阅 {kind} 推送")
        return
    await unsubscribe_kind(ev, steamid64, kind)
    await bot.send(f"已取消{scope_name(ev)}订阅的 {kind} 推送")


async def toggle_all_subscribe(bot: Bot, ev: Event, enable: bool) -> None:
    """全部推送类型的总开关。"""
    steamid64 = await _current_steamid64(ev)
    if enable:
        for kind in NOTIFY_KINDS:
            await subscribe_kind(ev, steamid64, kind)
        await bot.send(f"已为{scope_name(ev)}开启全部推送")
        return
    for kind in NOTIFY_KINDS:
        await unsubscribe_kind(ev, steamid64, kind)
    await bot.send(f"已关闭{scope_name(ev)}的全部推送")


async def _count_games(ev: Event, task_name: str) -> int:
    """当前会话订阅去重后的游戏数，口径与订阅列表一致。"""
    rows = await scope_task_rows(ev, task_name)
    return len({row.uid for row in rows if row.uid})


async def build_subscribe_status_text(ev: Event) -> str:
    """订阅状态：仅全局开启的类型按本会话账号判开关，公告 / 降价看本会话订阅数。

    未绑定账号时推送项无从判定，只出公告 / 降价数量。
    """
    lines = [f"{_PREFIX} {scope_name(ev)}订阅状态："]
    steamid64 = await get_main_steamid64(ev, ev.user_id)
    if steamid64 is not None:
        enabled = SteamConfig.get_config("NotifyTypes").data
        for kind in NOTIFY_KINDS:
            if kind not in enabled:
                continue
            state = "开" if await is_subscribed(ev, steamid64, kind) else "关"
            lines.append(f"- {kind}推送：{state}")
    lines.append(f"- 订阅公告数量：{await _count_games(ev, ANNOUNCE_TASK)}")
    lines.append(f"- 订阅降价数量：{await _count_games(ev, PRICE_TASK)}")
    return "\n".join(lines)
