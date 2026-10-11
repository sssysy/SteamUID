"""绑定原语：会话标识、绑定增删、订阅开关与登录态判断。

不含卡片组装：组装要用渲染层，render 在上、helper 在下，helper 不能反向引用。
"""

from collections.abc import Sequence

from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe

from ..database.model_auth import SteamAuth
from ..database.model_bind import SteamBind
from .notify import subscribe_task_name
from .status import NOTIFY_KINDS


def session_ids(ev: Event) -> tuple[str, str, str]:
    """绑定归属的会话标识：机器人、机器人账号、群号（私聊群号为空串）。"""
    return ev.bot_id, ev.bot_self_id, ev.group_id or ""


async def get_binds(ev: Event, user_id: str) -> list[SteamBind]:
    """取该会话内 user_id 的全部绑定。"""
    bot_id, bot_self_id, group_id = session_ids(ev)
    return await SteamBind.get_binds_by_session(user_id, bot_id, bot_self_id, group_id)


async def is_logged_in(steamid64: str) -> bool:
    """该 steamid 是否已存有可用令牌。"""
    account = await SteamAuth.get_account(steamid64)
    if account is None:
        return False
    return bool(account.access_token or account.refresh_token)


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
        steamid64=steamid64,
        WS_BOT_ID=ev.WS_BOT_ID,
        is_main_id=True,
    )
    for kind in default_kinds:
        await gs_subscribe.add_subscribe(
            "single", subscribe_task_name(kind), ev, uid=steamid64
        )


async def remove_bind(ev: Event, user_id: str, steamid64: str) -> None:
    """删除该会话内该 steamid 的绑定，并清掉它的通知订阅。"""
    bot_id, bot_self_id, group_id = session_ids(ev)
    await SteamBind.delete_bind(user_id, bot_id, bot_self_id, group_id, steamid64)
    for kind in NOTIFY_KINDS:
        await gs_subscribe.delete_subscribe(
            "single", subscribe_task_name(kind), ev, uid=steamid64
        )
