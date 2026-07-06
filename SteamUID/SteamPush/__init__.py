from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from ..utils.database.models import SteamBind
from ..SteamConfig import SteamConfig

push_SV = SV("steam推送开关")

push_status = {
    "push_start_game": "开始游戏",
    "push_end_game": "结束游戏",
    "push_archivement": "获得成就",
}

async def switch_push(bot:Bot, ev: Event, steamid64:str, push_column: list[str], status: bool):
    """切换推送状态"""
    if status:
        # 开启推送时才检查管理员开关
        push_switch = set(SteamConfig.get_config("PushSwitch").data)
        error_column = []
        fact_push_column = []
        for push_type in push_column:
            if push_status[push_type] not in push_switch:
                error_column.append(push_status[push_type])
            else:
                fact_push_column.append(push_type)
        if error_column:
            await bot.send(f"管理员未开放{' / '.join(error_column)}推送功能！")
        if not fact_push_column:
            return
    else:
        # 关闭推送不受管理员开关限制
        fact_push_column = push_column[:]

    subs = [s.steamid64 for s in await SteamBind.get_binds_by_user(ev.bot_id, ev.user_id, ev.user_type, ev.group_id)]
    if steamid64:
        # 传递了 steamid
        if steamid64 not in subs:
            return await bot.send("你没有绑定该 steamid，无法修改推送设置")
        else:
            # 传递了steamid64就修改为传入的steamid64
            subs = [steamid64]

    if not subs:
        return await bot.send("你没有绑定任何账号，无法修改推送设置")
    
    error_ids = set()
    for sub in subs:
        for push_type in fact_push_column:
            set_status = await SteamBind.set_push_status(sub, ev.bot_id, ev.user_id, ev.user_type, push_type, status, ev.group_id)
            if set_status != 0:
                error_ids.add(sub)

    if error_ids:
        await bot.send(f"{'\n'.join(error_ids)}\n推送状态切换失败")

    success_count = len(subs) - len(error_ids)
    if success_count == 0:
        return
    elif success_count < len(subs):
        return await bot.send("其余绑定的steamid推送状态切换成功")
    else:
        push_names = ' / '.join(push_status[p] for p in fact_push_column)
        if status:
            return await bot.send(f"{push_names}推送状态成功开启")
        else:
            return await bot.send(f"{push_names}推送状态成功关闭")


@push_SV.on_command("开启推送")
async def open_all_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_start_game", "push_end_game", "push_archivement"], True)



@push_SV.on_command("关闭推送")
async def close_all_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_start_game", "push_end_game", "push_archivement"], False)



@push_SV.on_command("开启开始游戏推送")
async def open_start_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_start_game"], True)



@push_SV.on_command("关闭开始游戏推送")
async def close_start_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_start_game"], False)



@push_SV.on_command("开启结束游戏推送")
async def open_end_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_end_game"], True)



@push_SV.on_command("关闭结束游戏推送")
async def close_end_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_end_game"], False)

@push_SV.on_command("开启成就推送")
async def open_archivement_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_archivement"], True)

@push_SV.on_command("关闭成就推送")
async def close_archivement_push(bot: Bot, ev: Event):
    steamid64 = ev.text.strip()
    await switch_push(bot, ev, steamid64, ["push_archivement"], False)


