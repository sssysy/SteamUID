import json

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from ..utils.database.models import SteamIDInfo, SteamBind
from ..utils.api import get_user_Summaries
from . import login
from ..SteamConfig import SteamConfig

bind_sv = SV("绑定账号")


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
    existing = await SteamBind.get_bind_by_steamid(steamid64)
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

    # 写绑定
    await SteamBind.upsert_bind(
        steamid64=steamid64,
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
        WS_BOT_ID=ev.WS_BOT_ID,
        group_id=ev.group_id,
        bot_self_id=ev.bot_self_id,
    )
    await bot.send(f"绑定 steamid: {steamid64} 成功")

    # 判断资料公开性，如果没公开就提醒一次用户
    visible = steamid_visible(steamid_info[0])
    if visible:
        await bot.send(visible)



@bind_sv.on_command(("绑定", "登录", "登陆", "bind"))
async def steambind(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    # 手动绑定
    if steamid64:
        if SteamConfig.get_config("OnlyOpenID").data:
            return await bot.send("仅允许网页登录，不支持手动绑定steamid！")
        else:
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

    # 删除绑定（返回 0 成功 / -1 未找到）
    result = await SteamBind.delete_bind(
        steamid64=steamid64,
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
    )
    if result != 0:
        return await bot.send("未找到绑定的项目")

    # 检查是否需要删除steamid缓存
    remaining = await SteamBind.get_bind_by_steamid(steamid64)
    if not remaining:
        await SteamIDInfo.delete_steamuserinfo(steamid64)

    await bot.send(f"解绑 steamid: {steamid64} 成功")

@bind_sv.on_command(("解绑", "unbind", "退出登录", "退出登陆"))
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
    subs = await SteamBind.get_binds_by_user(
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
    )
    if not subs:
        return await bot.send("未绑定任何 steamid")

    steamid_list = [sub.steamid64 for sub in subs if sub.steamid64]
    if not steamid_list:
        return await bot.send("未绑定任何 steamid")

    await bot.send(f"[steam] 已绑定的steamid：\n{'\n'.join(steamid_list)}")
