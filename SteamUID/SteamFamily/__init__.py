from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.subscribe import gs_subscribe

from ..utils.database.models import SteamBind
from ..utils.exceptions import SteamValidationError
from ..utils.helpers.command import steam_command
from .family_service import (
    FAMILY_TASK_NAME,
    build_family_wall_image,
    dump_family_baseline,
    fetch_family_snapshot,
)

family_SV = SV("steam家庭库相关")


async def _resolve_self_steamid64(ev: Event) -> str:
    steamid64 = await SteamBind.get_main_id(
        ev.bot_id, ev.user_id, ev.user_type, ev.group_id
    )
    if not steamid64:
        raise SteamValidationError("请先绑定 steam 账号")
    return steamid64


@steam_command("SteamFamily")
@family_SV.on_command("家庭游戏墙", block=True)
async def family_game_wall(bot: Bot, ev: Event):
    steamid64 = await _resolve_self_steamid64(ev)
    await bot.send("正在开始制作家庭游戏墙......")
    img_bytes = await build_family_wall_image(steamid64)
    await bot.send(MessageSegment.image(img_bytes))


@steam_command("SteamFamily")
@family_SV.on_command("订阅家庭库", block=True)
async def subscribe_family_library(bot: Bot, ev: Event):
    steamid64 = await _resolve_self_steamid64(ev)

    snapshot = await fetch_family_snapshot(steamid64)
    extra_data = dump_family_baseline(
        snapshot["family_groupid"],
        snapshot["family_name"],
        snapshot["appids"],
        snapshot["last_acquired_ts"],
    )
    await gs_subscribe.add_subscribe(
        subscribe_type="single",
        task_name=FAMILY_TASK_NAME,
        event=ev,
        uid=steamid64,
        extra_data=extra_data,
    )
    await bot.send(
        f"已订阅家庭库更新！\n"
        f"家庭：{snapshot.get('family_name')}\n"
        f"当前家庭库游戏数：{len(snapshot.get('appids') or [])}\n"
        f"后续检测到新增游戏时将通知您。"
    )


async def _unsubscribe_family_library(bot: Bot, ev: Event) -> None:
    steamid64 = await _resolve_self_steamid64(ev)
    await gs_subscribe.delete_subscribe(
        subscribe_type="single",
        task_name=FAMILY_TASK_NAME,
        event=ev,
        uid=steamid64,
        WS_BOT_ID=ev.WS_BOT_ID,
    )
    await bot.send("已取消订阅家庭库更新。")


@steam_command("SteamFamily")
@family_SV.on_command("退订家庭库", block=True)
async def unsubscribe_family_library(bot: Bot, ev: Event):
    await _unsubscribe_family_library(bot, ev)


@steam_command("SteamFamily")
@family_SV.on_command("取消订阅家庭库", block=True)
async def cancel_subscribe_family_library(bot: Bot, ev: Event):
    await _unsubscribe_family_library(bot, ev)
