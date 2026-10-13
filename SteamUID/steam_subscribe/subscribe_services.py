"""Steam 订阅推送开关与订阅状态查询的实现。"""

from collections.abc import Sequence

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..steam_config import SteamConfig
from ..utils.helper.bind import (
    is_subscribed,
    subscribe_kind,
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


def _subscribe_rows(rows: object) -> list[Subscribe]:
    """框架订阅查询无类型标注，这里立刻收窄为 Subscribe。"""
    if not isinstance(rows, Sequence):
        return []
    return [row for row in rows if isinstance(row, Subscribe)]


async def _count_games(ev: Event, task_name: str) -> int:
    """该用户在该 bot 下订阅去重后的游戏数，口径与订阅列表一致。"""
    rows = _subscribe_rows(
        await gs_subscribe.get_subscribe(
            task_name,
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
        )
    )
    return len({row.uid for row in rows if row.uid})


async def build_subscribe_status_text(ev: Event) -> str:
    """订阅状态：仅全局开启的类型按账号判开关，公告 / 降价看订阅游戏数。

    未绑定账号时推送项无从判定，只出公告 / 降价数量。
    """
    lines = [f"{_PREFIX} 订阅状态："]
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
