from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.database.models import SteamBind
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.utils import (
    PUSH_EVENTS,
    auto2steamid64,
    get_enabled_push_events,
    maybe_hide_steamid,
)

push_SV = SV("steam推送开关")


async def switch_push(
    ev: Event, steamid64: str, push_columns: list[str], enabled: bool
) -> str:
    """切换推送状态，成功返回结果消息"""
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
        target_sid = auto2steamid64(steamid64) or steamid64
        if target_sid not in subs:
            _raise("你没有绑定该 steamid，无法修改推送设置")
        else:
            subs = [target_sid]

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


# (命令关键字, 推送列名, 是否开启)
_PUSH_COMMANDS: list[tuple[tuple[str, ...], list[str], bool]] = [
    (("开启推送",), ["push_start_game", "push_end_game", "push_archivement"], True),
    (("关闭推送",), ["push_start_game", "push_end_game", "push_archivement"], False),
    (("开启开始游戏推送",), ["push_start_game"], True),
    (("关闭开始游戏推送",), ["push_start_game"], False),
    (("开启结束游戏推送",), ["push_end_game"], True),
    (("关闭结束游戏推送",), ["push_end_game"], False),
    (("开启成就推送",), ["push_archivement"], True),
    (("关闭成就推送",), ["push_archivement"], False),
]


def _make_handler(columns: list[str], enabled: bool):
    async def _handler(bot: Bot, ev: Event):
        try:
            text = ev.text.strip()
            steamid64 = auto2steamid64(text) or text
            result = await switch_push(ev, steamid64, columns, enabled)
            if result:
                await bot.send(result)
        except SteamError as e:
            await bot.send(str(e))
        except Exception as e:
            logger.exception(f"[SteamPush] 推送开关命令异常: {e!r}")
            await bot.send("发生未知错误，详情请查看后台。")

    return _handler


for _cmds, _columns, _enabled in _PUSH_COMMANDS:
    push_SV.on_command(_cmds)(_make_handler(_columns, _enabled))


@push_SV.on_command(("推送状态", "steam推送状态"))
async def check_push_status(bot: Bot, ev: Event):
    try:
        binds = await SteamBind.get_binds_by_user(
            ev.bot_id, ev.user_id, ev.user_type, ev.group_id
        )
        if not binds:
            await bot.send("你尚未绑定任何 Steam 账号！")
            return

        msg_lines = ["【Steam 推送状态】"]
        for b in binds:
            steamid_disp = maybe_hide_steamid(b.steamid64) if b.steamid64 else b.user_id
            msg_lines.append(f"账号：{steamid_disp}")
            msg_lines.append(f"  开始游戏推送：{'开启' if b.push_start_game else '关闭'}")
            msg_lines.append(f"  结束游戏推送：{'开启' if b.push_end_game else '关闭'}")
            msg_lines.append(f"  成就推送：{'开启' if b.push_archivement else '关闭'}")
            msg_lines.append(f"  自动探索队列：{'开启' if b.auto_discovery_queue else '关闭'}")
        await bot.send("\n".join(msg_lines))
    except Exception as e:
        logger.exception(f"[SteamPush] 查询推送状态异常: {e!r}")
        await bot.send("查询推送状态失败，详情请查看后台。")
