"""绑定原语：会话标识、绑定增删、订阅开关与登录态判断。

不含卡片组装：组装要用渲染层，render 在上、helper 在下，helper 不能反向引用。
"""

from collections.abc import Sequence

from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe

from .notify import subscribe_task_name
from .status import NOTIFY_KINDS
from ..database.model_auth import SteamAuth
from ..database.model_bind import SteamBind


def session_ids(ev: Event) -> tuple[str, str, str]:
    """绑定归属的会话标识：机器人、机器人账号、群号（私聊群号为空串）。"""
    return ev.bot_id, ev.bot_self_id, ev.group_id or ""


async def get_binds(ev: Event, user_id: str) -> list[SteamBind]:
    """取该会话内 user_id 的全部绑定。"""
    bot_id, bot_self_id, group_id = session_ids(ev)
    return await SteamBind.get_binds_by_session(user_id, bot_id, bot_self_id, group_id)


async def get_main_steamid64(ev: Event, user_id: str) -> str | None:
    """取该会话内 user_id 当前账号的 steamid64；未绑定返回 None。"""
    bot_id, bot_self_id, group_id = session_ids(ev)
    bind = await SteamBind.get_main_bind(user_id, bot_id, bot_self_id, group_id)
    if bind is None:
        return None
    return bind.steamid64


async def is_logged_in(steamid64: str) -> bool:
    """该 steamid 是否已存有可用令牌。"""
    account = await SteamAuth.get_account(steamid64)
    if account is None:
        return False
    return bool(account.access_token or account.refresh_token)


async def is_subscribed(ev: Event, steamid64: str, kind: str) -> bool:
    """该会话内该账号是否已订阅某类推送。"""
    rows = await gs_subscribe.get_subscribe(
        subscribe_task_name(kind),
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        uid=steamid64,
    )
    return bool(rows)


async def subscribe_kind(ev: Event, steamid64: str, kind: str) -> None:
    """按类型建立个人订阅，任务名与绑定默认订阅一致。"""
    await gs_subscribe.add_subscribe("single", subscribe_task_name(kind), ev, uid=steamid64)


async def unsubscribe_kind(ev: Event, steamid64: str, kind: str) -> None:
    """按类型取消个人订阅。"""
    await gs_subscribe.delete_subscribe("single", subscribe_task_name(kind), ev, uid=steamid64)


async def add_bind(
    ev: Event,
    user_id: str,
    steamid64: str,
    default_kinds: Sequence[str],
) -> None:
    """新增绑定并设为当前账户，同时按默认通知类型建立个人订阅。"""
    bot_id, bot_self_id, group_id = session_ids(ev)
    await SteamBind.upsert_bind(
        user_id=user_id,
        bot_id=bot_id,
        bot_self_id=bot_self_id,
        group_id=group_id,
        user_type=ev.user_type,
        steamid64=steamid64,
        WS_BOT_ID=ev.WS_BOT_ID,
        is_main_id=True,
    )
    for kind in default_kinds:
        await subscribe_kind(ev, steamid64, kind)


async def remove_bind(ev: Event, user_id: str, steamid64: str) -> None:
    """删除该会话内该 steamid 的绑定，并清掉它的通知订阅。"""
    bot_id, bot_self_id, group_id = session_ids(ev)
    await SteamBind.delete_bind(user_id, bot_id, bot_self_id, group_id, steamid64)
    for kind in NOTIFY_KINDS:
        await unsubscribe_kind(ev, steamid64, kind)
