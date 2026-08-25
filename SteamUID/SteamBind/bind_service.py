import json
import asyncio

from gsuid_core.models import Event

from ..utils.api import (
    get_user_Summaries,
    get_miniprofile,
    get_profile_items_equipped,
)
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
    ev: Event, steamid64: str, is_main_id: bool = True, is_asf: bool = False
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
                if not is_asf:
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
        is_asf=is_asf,
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

    # 如果存在 ASF Bot 实例，联动清理
    try:
        from ..SteamASFLogin.asf_client import ASFClient
        from ..SteamASFLogin.login import _sanitize_bot_name

        bot_name = _sanitize_bot_name(ev.user_id)
        await ASFClient.delete_bot(bot_name)
    except Exception:
        pass

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


async def _fetch_extra_profile(sid: str) -> tuple[str | None, str | None, str | None]:
    """并发获取 Steam 迷你资料与装备项，解析 (avatar_url, avatar_frame_url, bg_url)"""
    try:
        miniprofile_data, items_data = await asyncio.gather(
            get_miniprofile(sid),
            get_profile_items_equipped(sid),
            return_exceptions=True,
        )
    except Exception:
        miniprofile_data, items_data = {}, {}

    avatar_url = None
    if isinstance(miniprofile_data, dict) and miniprofile_data.get("avatar_url"):
        avatar_url = miniprofile_data["avatar_url"]

    avatar_frame_url = None
    if isinstance(items_data, dict):
        frame = items_data.get("avatar_frame", {})
        if frame.get("image_small"):
            avatar_frame_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{frame['image_small']}"
    if not avatar_frame_url and isinstance(miniprofile_data, dict):
        avatar_frame_url = miniprofile_data.get("avatar_frame")

    bg_img = None
    if isinstance(items_data, dict):
        mini_bg = items_data.get("mini_profile_background", {})
        if mini_bg.get("image_large"):
            bg_img = f"https://shared.fastly.steamstatic.com/community_assets/images/{mini_bg['image_large']}"
    if not bg_img and isinstance(miniprofile_data, dict):
        bg = miniprofile_data.get("profile_background", {})
        bg_img = bg.get("image")

    return avatar_url, avatar_frame_url, bg_img


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
        steamid64, name, avatar_url, avatar_frame_url, bg_url, avatar_hash, friend_code, is_main, warning
    """
    subs = await SteamBind.get_binds_by_user(
        bot_id=bot_id, user_id=user_id, user_type=user_type,
    )
    if not subs:
        return [], []

    unique_sids = list({sub.steamid64 for sub in subs})

    # 并发查询缺失的玩家摘要与迷你资料/头像框/背景
    extra_tasks = [_fetch_extra_profile(sid) for sid in unique_sids]
    extra_results = await asyncio.gather(*extra_tasks, return_exceptions=True)
    extra_map: dict[str, tuple[str | None, str | None, str | None]] = {}
    for sid, res in zip(unique_sids, extra_results):
        if isinstance(res, tuple):
            extra_map[sid] = res
        else:
            extra_map[sid] = (None, None, None)

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
        summary_avatar = info.get("avatarfull", info.get("avatarmedium", ""))
        avatar_hash = info.get("avatarhash", sub.steamid64)
        warning = check_steamid_visible(info)

        extra_avatar, avatar_frame_url, bg_url = extra_map.get(
            sub.steamid64, (None, None, None)
        )
        final_avatar = extra_avatar or summary_avatar

        item = {
            "steamid64": sub.steamid64,
            "name": name,
            "avatar_url": final_avatar,
            "avatar_frame_url": avatar_frame_url,
            "bg_url": bg_url,
            "avatar_hash": avatar_hash,
            "friend_code": steamid64_to_friend_code(sub.steamid64),
            "is_main": bool(sub.is_main_id and sub.group_id == group_id),
            "is_asf": bool(getattr(sub, "is_asf", False)),
            "warning": warning,
        }

        if sub.group_id == group_id:
            now_items.append(item)
        else:
            if show_all:
                other_items.append(item)

    return now_items, other_items
