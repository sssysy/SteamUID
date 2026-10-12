"""Steam 账号绑定命令：绑定 / 解绑 / 查看 / 切换 / 刷新用户。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..steam_config import SteamConfig
from .bind_services import (
    bind_account,
    send_bind_card,
    switch_account,
    unbind_account,
    refresh_bind_card,
    request_openid_login,
)
from ..utils.helper.command import command_guard, resolve_target

bind_sv = SV("Steam绑定账号")


@bind_sv.on_command("绑定")
@command_guard
async def steam_bind(bot: Bot, ev: Event) -> None:
    user_id, steamid64 = resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await request_openid_login(bot, ev)
    await bind_account(ev, user_id, steamid64)
    await send_bind_card(bot, ev, user_id)


@bind_sv.on_command("解绑")
@command_guard
async def steam_unbind(bot: Bot, ev: Event) -> None:
    user_id, steamid64 = resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await request_openid_login(bot, ev)
    await unbind_account(ev, user_id, steamid64)
    await send_bind_card(bot, ev, user_id)


@bind_sv.on_command("查看")
@command_guard
async def steam_view(bot: Bot, ev: Event) -> None:
    user_id, _ = resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    await send_bind_card(bot, ev, user_id)


@bind_sv.on_command("切换", block=True)
@command_guard
async def steam_switch(bot: Bot, ev: Event) -> None:
    """steam切换[好友码|序号]：切换当前账号；无参数则切到下一位。"""
    await bot.send(await switch_account(ev, ev.user_id, ev.text))


@bind_sv.on_fullmatch("刷新用户", block=True)
@command_guard
async def steam_refresh_user(bot: Bot, ev: Event) -> None:
    """steam刷新用户：重拉当前会话绑定账号的资料并重发卡片。"""
    await refresh_bind_card(bot, ev, ev.user_id)
