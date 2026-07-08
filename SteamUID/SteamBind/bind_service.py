import json

from gsuid_core.models import Event

from ..utils.api import get_user_Summaries
from ..utils.database.models import SteamIDInfo, SteamBind
from ..utils.exceptions import SteamValidationError


async def update_steam_info(steamid64: str, steamid_info: list) -> bool:
    if not steamid_info:
        return False
    player = steamid_info[0]
    await SteamIDInfo.upsert_steamuserinfo(
        steamid64, json.dumps(player, ensure_ascii=False)
    )
    return True


def check_steamid_visible(player: dict) -> str:
    visible = player.get("communityvisibilitystate", 4)
    if visible == 1:
        return "注意：当前绑定steamid状态未公开，无法获取状态变更信息！"
    elif visible == 2:
        return "注意：当前绑定steamid状态仅限好友查看，可能无法获取状态变更信息！"
    else:
        return ""


async def do_bind(
    ev: Event, steamid64: str, is_main_id: bool = True
) -> tuple[str, str]:
    """成功返回 (成功消息, 可见性提醒)，校验失败 raise SteamValidationError"""
    if not steamid64 or not steamid64.isdigit():
        raise SteamValidationError("请输入正确的64位steamid")

    existing = await SteamBind.get_bind_by_steamid(steamid64)
    if existing:
        is_self = any(
            sub.user_id == ev.user_id and sub.bot_id == ev.bot_id
            for sub in existing
        )
        if is_self:
            is_binding_here = any(
                sub.group_id == ev.group_id
                for sub in existing if sub.user_id == ev.user_id and sub.bot_id == ev.bot_id
            )
            if is_binding_here:
                raise SteamValidationError("你已在该群绑定该steamid！")
        else:
            raise SteamValidationError("该steamid已被他人绑定！")

    steamid_info = await get_user_Summaries(steamid64)
    if not await update_steam_info(steamid64, steamid_info):
        raise SteamValidationError("该steamid不存在")

    await SteamBind.upsert_bind(
        steamid64=steamid64,
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
        WS_BOT_ID=ev.WS_BOT_ID,
        group_id=ev.group_id,
        bot_self_id=ev.bot_self_id,
        is_main_id=is_main_id,
    )
    success_msg = f"绑定 steamid: {steamid64} 成功"

    warning = check_steamid_visible(steamid_info[0])
    return success_msg, warning


async def do_unbind(ev: Event, steamid64: str) -> str:
    if not steamid64 or not steamid64.isdigit():
        raise SteamValidationError("请输入正确的64位steamid")

    result = await SteamBind.delete_bind(
        steamid64=steamid64,
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
        group_id=ev.group_id,
    )
    if result != 0:
        raise SteamValidationError("未找到绑定的项目")

    # 无其他绑定者时清理缓存
    remaining = await SteamBind.get_bind_by_steamid(steamid64)
    if not remaining:
        await SteamIDInfo.delete_steamuserinfo(steamid64)

    return f"解绑 steamid: {steamid64} 成功"


async def format_bind_list(
    bot_id: str,
    user_id: str,
    user_type: str,
    show_all: bool,
    group_id: str | None = None,
) -> str | None:
    subs = await SteamBind.get_binds_by_user(
        bot_id=bot_id,
        user_id=user_id,
        user_type=user_type,
    )
    if not subs:
        return None

    now_id_list = []
    other_id_list = []
    for sub in subs:
        tag = " [主]" if (sub.is_main_id and sub.group_id == group_id) else ""
        entry = f"{sub.steamid64}{tag}"
        if sub.group_id == group_id:
            now_id_list.append(entry)
        else:
            other_id_list.append(entry)

    now_id_list = list(set(now_id_list))
    other_id_list = list(set(other_id_list))

    if not now_id_list and not other_id_list:
        return None

    sep = "-" * 20
    now_ids = "\n".join(now_id_list)
    other_ids = "\n".join(other_id_list)

    send_msg = f"[steam] -=绑定列表=-\n{sep}\n"
    if now_id_list:
        send_msg += f"此群已绑定的steamid：\n{now_ids}\n{sep}\n"
    if other_id_list and show_all:
        send_msg += f"其他地方已绑定的steamid：\n{other_ids}\n{sep}\n"

    return send_msg


async def switch_main_id(ev: Event, steamid64: str) -> str:
    all_binds = await SteamBind.get_binds_by_user(
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
    )
    all_steamid64 = [bind.steamid64 for bind in all_binds]
    if steamid64 not in all_steamid64:
        raise SteamValidationError("未绑定当前steamid!")

    await SteamBind.set_main_id(
        steamid64=steamid64,
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
        group_id=ev.group_id,
    )
    return f"切换 steamid: {steamid64} 成功"
