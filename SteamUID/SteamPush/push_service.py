from gsuid_core.models import Event

from ..utils.database.models import SteamBind
from ..utils.exceptions import SteamValidationError
from ..utils.steam_status import PUSH_EVENTS, get_enabled_push_events
from ..utils.utils import maybe_hide_steamid


async def switch_push(
    ev: Event, steamid64: str, push_columns: list[str], enabled: bool
) -> str:
    """切换推送状态，成功返回结果消息，校验失败 raise SteamValidationError"""
    messages: list[str] = []

    if enabled:
        push_switch = get_enabled_push_events()
        error_column = []
        fact_push_column = []
        for push_type in push_columns:
            if PUSH_EVENTS[push_type] not in push_switch:
                error_column.append(PUSH_EVENTS[push_type])
            else:
                fact_push_column.append(push_type)
        if error_column:
            messages.append(f"管理员未开放{' / '.join(error_column)}推送功能！")
        if not fact_push_column:
            return "\n".join(messages)
    else:
        fact_push_column = push_columns[:]

    def _raise(msg: str) -> None:
        if messages:
            raise SteamValidationError("\n".join(messages) + "\n" + msg)
        raise SteamValidationError(msg)

    subs = [
        s.steamid64
        for s in await SteamBind.get_binds_by_user(
            ev.bot_id, ev.user_id, ev.user_type, ev.group_id
        )
    ]
    if steamid64:
        if steamid64 not in subs:
            _raise("你没有绑定该 steamid，无法修改推送设置")
        else:
            subs = [steamid64]

    if not subs:
        _raise("你没有绑定任何账号，无法修改推送设置")

    error_ids = set()
    for sub in subs:
        for push_type in fact_push_column:
            set_status = await SteamBind.set_push_status(
                sub,
                ev.bot_id,
                ev.user_id,
                ev.user_type,
                push_type,
                enabled,
                ev.group_id,
            )
            if set_status != 0:
                error_ids.add(sub)

    if error_ids:
        failed_ids = "\n".join(maybe_hide_steamid(sid) for sid in error_ids)
        messages.append(f"{failed_ids}\n推送状态切换失败")

    success_count = len(subs) - len(error_ids)
    if success_count == 0:
        return "\n".join(messages)
    elif success_count < len(subs):
        messages.append("其余绑定的steamid推送状态切换成功")
        return "\n".join(messages)
    else:
        push_names = " / ".join(PUSH_EVENTS[p] for p in fact_push_column)
        if enabled:
            messages.append(f"{push_names}推送状态成功开启")
        else:
            messages.append(f"{push_names}推送状态成功关闭")
        return "\n".join(messages)
