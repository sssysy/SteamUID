"""绑定原语：会话标识、绑定增删、订阅开关与登录态判断。

不含卡片组装：组装要用渲染层，render 在上、helper 在下，helper 不能反向引用。
"""

from collections.abc import Sequence

from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

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


def subscribe_rows(raw: object) -> list[Subscribe]:
    """框架订阅接口无类型标注，这里立刻收窄为 Subscribe。"""
    if not isinstance(raw, Sequence):
        return []
    return [row for row in raw if isinstance(row, Subscribe)]


def scope_name(ev: Event) -> str:
    """会话自称：群为 [本群]，私聊为 [您]。"""
    return "本群" if ev.group_id else "您"


def _in_scope(ev: Event, rows: Sequence[Subscribe]) -> list[Subscribe]:
    """群行看 group_id、私聊行看 user_id，判定是否属于当前会话。"""
    if ev.group_id:
        return [row for row in rows if row.group_id == ev.group_id]
    return [row for row in rows if not row.group_id and row.user_id == ev.user_id]


async def scope_subscribe_rows(ev: Event, task_name: str, uid: str) -> list[Subscribe]:
    """取当前会话对某个 uid 的订阅行。"""
    return _in_scope(ev, subscribe_rows(await gs_subscribe.get_subscribe(task_name, uid=uid)))


async def scope_task_rows(ev: Event, task_name: str) -> list[Subscribe]:
    """取当前会话某个任务下的全部订阅行。"""
    return _in_scope(ev, subscribe_rows(await gs_subscribe.get_subscribe(task_name)))


async def delete_scope_subscribe(ev: Event, task_name: str, uid: str) -> None:
    """删除当前会话的订阅行；连带清掉 bot_self_id 为空的遗留行，否则永远关不掉。"""
    base: dict[str, str] = {"task_name": task_name, "uid": uid, "bot_id": ev.bot_id}
    if ev.group_id:
        await Subscribe.delete_row(**base, group_id=ev.group_id, bot_self_id=ev.bot_self_id)
        await Subscribe.delete_row(**base, group_id=ev.group_id, bot_self_id="")
        return
    # 群行也带 user_id，私聊路径必须限定 group_id 为空，否则会删掉该用户所有群的订阅
    await Subscribe.delete_row(**base, user_id=ev.user_id, group_id=None, bot_self_id=ev.bot_self_id)
    await Subscribe.delete_row(**base, user_id=ev.user_id, group_id=None, bot_self_id="")


async def add_scope_subscribe(
    ev: Event,
    task_name: str,
    uid: str,
    *,
    extra_message: str | None = None,
    extra_data: str | None = None,
) -> None:
    """按会话写入订阅：群行交给框架 session 判重，私聊行自写，避免把群行改成私聊行。"""
    if ev.group_id:
        await gs_subscribe.add_subscribe(
            "session",
            task_name,
            ev,
            extra_message=extra_message,
            uid=uid,
            extra_data=extra_data,
        )
        return
    await delete_scope_subscribe(ev, task_name, uid)
    await Subscribe.full_insert_data(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        group_id=ev.group_id,
        task_name=task_name,
        bot_self_id=ev.bot_self_id,
        user_type=ev.user_type,
        extra_message=extra_message,
        WS_BOT_ID=ev.WS_BOT_ID,
        uid=uid,
        extra_data=extra_data,
        msg_id=ev.msg_id,
    )


async def is_subscribed(ev: Event, steamid64: str, kind: str) -> bool:
    """当前会话是否已订阅该账号的某类推送。"""
    return bool(await scope_subscribe_rows(ev, subscribe_task_name(kind), steamid64))


async def subscribe_kind(ev: Event, steamid64: str, kind: str) -> None:
    """按类型建立会话订阅：群内一份、私聊本人一份，任务名与绑定默认订阅一致。"""
    await add_scope_subscribe(ev, subscribe_task_name(kind), steamid64)


async def unsubscribe_kind(ev: Event, steamid64: str, kind: str) -> None:
    """按类型取消当前会话的订阅。"""
    await delete_scope_subscribe(ev, subscribe_task_name(kind), steamid64)


async def add_bind(
    ev: Event,
    user_id: str,
    steamid64: str,
    default_kinds: Sequence[str],
) -> None:
    """新增绑定并设为当前账户，同时按默认通知类型建立会话订阅。"""
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
