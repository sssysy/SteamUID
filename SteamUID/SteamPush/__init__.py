from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from ..utils.database.models import SteamBind
from ..SteamConfig import SteamConfig

push_SV = SV("steam推送开关")

"""
===============
等待后续有空了重构
===============
"""

@push_SV.on_command("开启推送")
async def open_all_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    push_switch = set(SteamConfig.get_config("PushSwitch").data)
    if not {"开始游戏", "结束游戏"}.issubset(push_switch):
        return await bot.send("管理员未开放游戏/结束游戏推送功能！")

    if not steamid64:
        # 没有传递 steamid
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if not subs:
            return await bot.send("你没有绑定任何账号，无法开启推送")

        for sub in subs:
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", True)
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", True)
        return await bot.send("已开启绑定的所有 steamid 开始 / 结束游戏推送")

    else:
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if steamid64 not in [s.steamid64 for s in subs]:
            return await bot.send("你没有绑定该 steamid，无法开启推送")

        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", True)
        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", True)
        return await bot.send(f"已开启 steamid: {steamid64} 开始 / 结束游戏推送")


@push_SV.on_command("关闭推送")
async def close_all_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    push_switch = set(SteamConfig.get_config("PushSwitch").data)
    if not {"开始游戏", "结束游戏"}.issubset(push_switch):
        return await bot.send("管理员未开放游戏/结束游戏推送功能！")

    if not steamid64:
        # 没有传递 steamid
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if not subs:
            return await bot.send("你没有绑定任何账号，无需关闭推送")

        for sub in subs:
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", False)
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", False)
        return await bot.send("已关闭绑定的所有 steamid 开始 / 结束游戏推送")

    else:
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if steamid64 not in [s.steamid64 for s in subs]:
            return await bot.send("你没有绑定该 steamid，无法关闭推送")

        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", False)
        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", False)
        return await bot.send(f"已关闭 steamid: {steamid64} 开始 / 结束游戏推送")

@push_SV.on_command("开启开始游戏推送")
async def open_start_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    push_switch = set(SteamConfig.get_config("PushSwitch").data)
    if "开始游戏" not in push_switch:
        return await bot.send("管理员未开放开始游戏推送功能！")
    
    if not steamid64:
        # 没有传递 steamid
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if not subs:
            return await bot.send("你没有绑定任何账号，无法开启开始游戏推送")

        for sub in subs:
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", True)
        return await bot.send("已开启绑定的所有 steamid 开始游戏推送")

    else:
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if steamid64 not in [s.steamid64 for s in subs]:
            return await bot.send("你没有绑定该 steamid，无法开启开始游戏推送")

        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", True)
        return await bot.send(f"已开启 steamid: {steamid64} 开始游戏推送")

@push_SV.on_command("关闭开始游戏推送")
async def close_start_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    push_switch = set(SteamConfig.get_config("PushSwitch").data)
    if "开始游戏" not in push_switch:
        return await bot.send("管理员未开放开始游戏推送功能！")
    
    if not steamid64:
        # 没有传递 steamid
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if not subs:
            return await bot.send("你没有绑定任何账号，无需关闭开始游戏推送")
        
        for sub in subs:
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", False)
        return await bot.send("已关闭绑定的所有 steamid 开始游戏推送")
    
    else:
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if steamid64 not in [s.steamid64 for s in subs]:
            return await bot.send("你没有绑定该 steamid，无法关闭开始游戏推送")

        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_start_game", False)
        return await bot.send(f"已关闭 steamid: {steamid64} 开始游戏推送")

@push_SV.on_command("开启结束游戏推送")
async def open_end_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    push_switch = set(SteamConfig.get_config("PushSwitch").data)
    if "结束游戏" not in push_switch:
        return await bot.send("管理员未开放结束游戏推送功能！")
    
    if not steamid64:
        # 没有传递 steamid
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if not subs:
            return await bot.send("你没有绑定任何账号，无法开启结束游戏推送")
        
        for sub in subs:
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", True)
        return await bot.send("已开启绑定的所有 steamid 结束游戏推送")
    
    else:
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if steamid64 not in [s.steamid64 for s in subs]:
            return await bot.send("你没有绑定该 steamid，无法开启结束游戏推送")

        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", True)
        return await bot.send(f"已开启 steamid: {steamid64} 结束游戏推送")

@push_SV.on_command("关闭结束游戏推送")
async def close_end_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    push_switch = set(SteamConfig.get_config("PushSwitch").data)
    if "结束游戏" not in push_switch:
        return await bot.send("管理员未开放结束游戏推送功能！")

    if not steamid64:
        # 没有传递 steamid
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if not subs:
            return await bot.send("你没有绑定任何账号，无法关闭结束游戏推送")
        
        for sub in subs:
            await SteamBind.set_push_status(sub.steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", False)
        return await bot.send("已关闭绑定的所有 steamid 结束游戏推送")
    
    else:
        subs = await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type)
        if steamid64 not in [s.steamid64 for s in subs]:
            return await bot.send("你没有绑定该 steamid，无法关闭结束游戏推送")

        await SteamBind.set_push_status(steamid64, ev.bot_id, ev.user_id,ev.user_type, "push_end_game", False)
        return await bot.send(f"已关闭 steamid: {steamid64} 结束游戏推送")
