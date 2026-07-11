import json

from gsuid_core.models import Event

from ..utils.api import get_user_Summaries
from ..utils.database.models import SteamIDInfo, SteamBind
from ..utils.exceptions import SteamValidationError
from ..utils.utils import steamid64_to_friend_code, maybe_hide_steamid
from ..SteamConfig import SteamConfig



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

def get_push_default(name: str) -> bool:
    """获取默认开启推送事件"""
    pushdefault = SteamConfig.get_config("PushDefault").data
    if name in pushdefault:
        return True
    else:
        return False

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
        push_start_game=get_push_default("开始游戏"),
        push_end_game=get_push_default("结束游戏"),
        push_archivement=get_push_default("获得成就"),
    )
    success_msg = f"绑定 steamid: {maybe_hide_steamid(steamid64)} 成功"

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

    return f"解绑 steamid: {maybe_hide_steamid(steamid64)} 成功"


async def format_bind_list(
    bot_id: str,
    user_id: str,
    user_type: str,
    show_all: bool,
    group_id: str | None = None,
) -> str | None:
    """格式化绑定列表"""
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
        entry = f"{maybe_hide_steamid(sub.steamid64)}{tag}"
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
    return f"切换 steamid: {maybe_hide_steamid(steamid64)} 成功"


async def get_bind_card_data(
    bot_id: str,
    user_id: str,
    user_type: str,
    group_id: str | None,
    show_all: bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    获取绑定列表的卡片渲染数据。

    返回 (本群绑定列表, 其他群绑定列表)，每项包含:
        steamid64, name, avatar_url, avatar_hash, friend_code, is_main, warning
    """
    subs = await SteamBind.get_binds_by_user(
        bot_id=bot_id, user_id=user_id, user_type=user_type,
    )
    if not subs:
        return [], []

    now_items: list[dict] = []
    other_items: list[dict] = []

    for sub in subs:
        # 读取缓存的玩家信息
        info_json = await SteamIDInfo.get_steamuserinfo(sub.steamid64)
        if info_json:
            info = json.loads(info_json)
        else:
            # 缓存缺失，从 API 获取
            steamid_info = await get_user_Summaries(sub.steamid64)
            if steamid_info:
                info = steamid_info[0]
                await SteamIDInfo.upsert_steamuserinfo(
                    sub.steamid64, json.dumps(info, ensure_ascii=False)
                )
            else:
                info = {}

        name = info.get("personaname", "未知用户")
        avatar_url = info.get("avatarfull", info.get("avatarmedium", ""))
        avatar_hash = info.get("avatarhash", sub.steamid64)
        warning = check_steamid_visible(info)

        item = {
            "steamid64": sub.steamid64,
            "name": name,
            "avatar_url": avatar_url,
            "avatar_hash": avatar_hash,
            "friend_code": steamid64_to_friend_code(sub.steamid64),
            "is_main": bool(sub.is_main_id and sub.group_id == group_id),
            "warning": warning,
        }

        if sub.group_id == group_id:
            now_items.append(item)
        else:
            if show_all:
                other_items.append(item)

    return now_items, other_items
