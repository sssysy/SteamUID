import json

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from ..utils.database.models import SteamIDInfo
from ..utils.api import get_user_Summaries

bind_sv = SV("绑定账号")

# 订阅主题：每个 steamid64 作为 uid 存入 Subscribe 表
STEAM_POLL_TASK = "SteamPoll"


async def update_steam_info(steamid64: str, steamid_info: list) -> bool:
    """拉取并缓存 Steam 用户信息（静默，不发消息）

    返回 True 表示成功拉取并缓存；False 表示该 steamid 无效（API 返回空）。
    缓存单个 player dict（非整个 players 列表），与轮询时的单条 info 类型对齐。
    """
    if not steamid_info:
        return False
    # 单 ID 查询返回长度为 1 的列表，取第一个 player
    player = steamid_info[0]
    await SteamIDInfo.upsert_steamuserinfo(
        steamid64, json.dumps(player, ensure_ascii=False)
    )
    return True


def steamid_visible(player: dict) -> str:
    """判断 steamid 是否可见"""
    visible = player.get("communityvisibilitystate", 4)
    if visible == 1:
        return "注意：当前绑定steamid状态未公开，无法获取状态变更信息！"
    elif visible == 2:
        return "注意：当前绑定steamid状态仅限好友查看，可能无法获取状态变更信息！"
    else:
        return ""


@bind_sv.on_prefix("绑定")
async def steambind(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    if not steamid64 or not steamid64.isdigit():
        return await bot.send("请输入正确的64位steamid")

    # 检查该 steamid64 是否已被他人绑定（一个 ID 只能一人绑定）
    existing = await gs_subscribe.get_subscribe(STEAM_POLL_TASK, uid=steamid64)
    if existing:
        # 已存在订阅：与 add_subscribe 的 single 模式去重逻辑对齐，只比 user_id+bot_id
        is_self = any(
            sub.user_id == ev.user_id and sub.bot_id == ev.bot_id
            for sub in existing
        )
        if is_self:
            return await bot.send("你已绑定该steamid！")
        return await bot.send("该steamid已被他人绑定！")

    # 先验证 steamid 有效性并缓存用户信息，避免无效 ID 写入订阅
    steamid_info = await get_user_Summaries(steamid64)
    if not await update_steam_info(steamid64, steamid_info):
        return await bot.send("该steamid不存在")

    # 写入订阅（single 模式：同 user 可绑多个不同 uid）
    await gs_subscribe.add_subscribe("single", STEAM_POLL_TASK, ev, uid=steamid64)
    await bot.send("绑定成功")

    # 判断资料公开性，如果没公开就提醒一次用户
    visible = steamid_visible(steamid_info[0])
    if visible:
        await bot.send(visible)


@bind_sv.on_prefix("解绑")
async def steamunbind(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    if not steamid64 or not steamid64.isdigit():
        return await bot.send("请输入正确的64位steamid")

    # 检查该用户是否绑定了此 steamid64
    existing = await gs_subscribe.get_subscribe(
        STEAM_POLL_TASK,
        uid=steamid64,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
    )
    if not existing:
        return await bot.send("未找到绑定的项目")

    # 删除订阅
    await gs_subscribe.delete_subscribe("single", STEAM_POLL_TASK, ev, uid=steamid64)

    # 复查是否真的删除成功（并发场景下可能已被删过）
    still_exist = await gs_subscribe.get_subscribe(
        STEAM_POLL_TASK,
        uid=steamid64,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
    )
    if still_exist:
        return await bot.send("解绑失败，请稍后重试")

    # 检查该 steamid64 是否还有其他订阅者，无则清理缓存
    remaining = await gs_subscribe.get_subscribe(STEAM_POLL_TASK, uid=steamid64)
    if not remaining:
        await SteamIDInfo.delete_steamuserinfo(steamid64)

    await bot.send("解绑成功")


@bind_sv.on_command("查看")
async def steamview(bot: Bot, ev: Event):
    # 查询该用户绑定的所有 steamid64
    subs = await gs_subscribe.get_subscribe(
        STEAM_POLL_TASK,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
    )
    if not subs:
        return await bot.send("未绑定任何 steamid")

    steamid_list = [sub.uid for sub in subs if sub.uid]
    if not steamid_list:
        return await bot.send("未绑定任何 steamid")

    await bot.send(f"已绑定的steamid：{','.join(steamid_list)}")
