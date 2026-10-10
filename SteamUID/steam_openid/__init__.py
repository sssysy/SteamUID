"""Steam OpenID 绑定命令：绑定 / 解绑 / 查看。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..steam_config import get_allow_at
from .openid_services import (
    bind_account,
    send_bind_card,
    unbind_account,
    request_openid_login,
)
from ..utils.helper.command import command_guard, resolve_target

bind_sv = SV("Steam绑定账号")


@bind_sv.on_command("绑定")
@command_guard
async def steam_bind(bot: Bot, ev: Event) -> None:
    user_id, steamid64 = resolve_target(ev, allow_at=get_allow_at())
    if steamid64 is None:
        steamid64 = await request_openid_login(bot, ev)
    await bind_account(ev, user_id, steamid64)
    await send_bind_card(bot, ev, user_id)


@bind_sv.on_command("解绑")
@command_guard
async def steam_unbind(bot: Bot, ev: Event) -> None:
    user_id, steamid64 = resolve_target(ev, allow_at=get_allow_at())
    if steamid64 is None:
        steamid64 = await request_openid_login(bot, ev)
    await unbind_account(ev, user_id, steamid64)
    await send_bind_card(bot, ev, user_id)


@bind_sv.on_command("查看")
@command_guard
async def steam_view(bot: Bot, ev: Event) -> None:
    user_id, _ = resolve_target(ev, allow_at=get_allow_at())
    await send_bind_card(bot, ev, user_id)
