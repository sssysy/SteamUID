import json

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from ..utils.database.models import SteamIDInfo
from ..utils.api import get_user_Summaries
from . import login

bind_sv = SV("绑定账号")

# 订阅
STEAM_POLL_TASK = "SteamPoll"


async def update_steam_info(steamid64: str, steamid_info: list) -> bool:
    """拉取缓存 Steam 用户信息"""
    if not steamid_info:
        return False
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


async def do_bind(bot: Bot, ev: Event, steamid64: str):
    """绑定 steam 主函数"""
    if not steamid64 or not steamid64.isdigit():
        return await bot.send("请输入正确的64位steamid")

    # id 已被绑定
    existing = await gs_subscribe.get_subscribe(STEAM_POLL_TASK, uid=steamid64)
    if existing:
        # 已订阅
        is_self = any(
            sub.user_id == ev.user_id and sub.bot_id == ev.bot_id
            for sub in existing
        )
        if is_self:
            return await bot.send("你已绑定该steamid！")
        else:
            return await bot.send("该steamid已被他人绑定！")

    # 取 steamid 信息
    steamid_info = await get_user_Summaries(steamid64)
    if not await update_steam_info(steamid64, steamid_info):
        return await bot.send("该steamid不存在")

    # 写订阅
    await gs_subscribe.add_subscribe("single", STEAM_POLL_TASK, ev, uid=steamid64)
    await bot.send("绑定成功")

    # 判断资料公开性，如果没公开就提醒一次用户
    visible = steamid_visible(steamid_info[0])
    if visible:
        await bot.send(visible)



@bind_sv.on_command("绑定")
async def steambind(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    # 手动绑定
    if steamid64:
        await do_bind(bot, ev, steamid64)

    # 自动绑定
    else:
        steamid64 = await login.request_openid_login(bot, ev)
        if steamid64:
            await do_bind(bot, ev, steamid64)


async def do_unbind(bot: Bot, ev: Event, steamid64: str):
    """解绑主函数"""
    if not steamid64 or not steamid64.isdigit():
        return await bot.send("请输入正确的64位steamid")

    # 查绑定状态
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

    # 复查
    still_exist = await gs_subscribe.get_subscribe(
        STEAM_POLL_TASK,
        uid=steamid64,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
    )
    if still_exist:
        return await bot.send("解绑失败，请稍后重试")

    # 检查是否需要删除steamid缓存
    remaining = await gs_subscribe.get_subscribe(STEAM_POLL_TASK, uid=steamid64)
    if not remaining:
        await SteamIDInfo.delete_steamuserinfo(steamid64)

    await bot.send("解绑成功")

@bind_sv.on_command("解绑")
async def steamunbind(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    # 手动解绑
    if steamid64:
        await do_unbind(bot, ev, steamid64)
    # 自动解绑
    else:
        await bot.send("请在接下来登录一次要解绑的 steam 以继续")
        steamid64 = await login.request_openid_login(bot, ev)
        if steamid64:
            await do_unbind(bot, ev, steamid64)


@bind_sv.on_command("查看")
async def steamview(bot: Bot, ev: Event):
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
