"""扫码登录流程：发起会话、发送二维码、轮询、落库与自动绑定。"""

import time
import json
import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment

from ..steam_config import get_default_notify_types
from ..utils.api.auth import generate_session_id
from ..utils.api.models import QrReady
from ..utils.api.qr_login import SteamQrLogin
from ..utils.database.model_auth import SteamAuth
from ..utils.helper.bind import add_bind, get_binds
from ..utils.render.bind_card import render_bind_card_image
from ..utils.render.pil.render_qr import render_qr_png

_TAG = "[Steam·扫码登录]"
_PREFIX = "[Steam]"
# 提示文案的有效期与轮询上限共用它，改动时文案自动同步
_QR_TTL_SECONDS = 120.0


def _at_user(ev: Event) -> Message:
    return MessageSegment.at(ev.user_id)


async def _notify(bot: Bot, ev: Event, text: str) -> None:
    """按 @用户 + [Steam] 的固定格式发一条普通消息。"""
    await bot.send([_at_user(ev), MessageSegment.text(f" {_PREFIX} {text}")])


def _login_hint(user_id: str) -> str:
    minutes = int(_QR_TTL_SECONDS // 60)
    return (
        f'请使用 "Steam" App 扫描上方二维码进行登录。有效期 {minutes} 分钟\n'
        "注意：扫码登录后将获取到对应Steam账户的大部分权限，请谨慎操作！\n"
        f"校验码：{user_id}"
    )


async def _wait_for_confirm(
    bot: Bot,
    ev: Event,
    session: SteamQrLogin,
    interval: float,
) -> QrReady | None:
    """按服务端下发间隔轮询，直到确认或超时；扫码后先提示一次等待确认。"""
    deadline = time.monotonic() + _QR_TTL_SECONDS
    scanned_notified = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        await asyncio.sleep(min(interval, remaining))
        status = await session.poll()
        if status["done"]:
            return status
        if status["scanned"] and not scanned_notified:
            scanned_notified = True
            await _notify(bot, ev, "扫码成功，请在手机上点击确认登录按钮")


async def _complete_login(bot: Bot, ev: Event, ready: QrReady) -> None:
    """写凭据，未绑定时自动绑定，最后回发绑定列表卡片。"""
    steamid64 = ready["steamid64"]
    session_id = generate_session_id()
    cookies = {
        "sessionid": session_id,
        "steamLoginSecure": f"{steamid64}||{ready['access_token']}",
    }
    await SteamAuth.upsert_account(
        steamid64=steamid64,
        account_name=ready["account_name"],
        access_token=ready["access_token"],
        refresh_token=ready["refresh_token"],
        session_id=session_id,
        cookies_json=json.dumps(cookies),
        updated_at=int(time.time()),
    )

    binds = await get_binds(ev, ev.user_id)
    if not any(bind.steamid64 == steamid64 for bind in binds):
        await add_bind(ev, ev.user_id, steamid64, get_default_notify_types())

    image = await render_bind_card_image(ev, ev.user_id)
    await bot.send(MessageSegment.image(image))
    logger.info(f"{_TAG} 账号 {steamid64} 扫码登录成功")


async def start_qr_login(bot: Bot, ev: Event) -> None:
    """扫码登录主流程：二维码 → 轮询确认 → 落库绑定 → 回卡片。"""
    async with SteamQrLogin() as session:
        challenge = await session.begin()
        image = await render_qr_png(challenge["challenge_url"])
        await bot.send(
            MessageSegment.node(
                [
                    MessageSegment.image(image),
                    _at_user(ev),
                    MessageSegment.text(f" {_PREFIX} {_login_hint(ev.user_id)}"),
                ]
            )
        )
        ready = await _wait_for_confirm(bot, ev, session, challenge["interval"])

    if ready is None:
        await _notify(bot, ev, "登录超时，请重新登录。")
        return
    await _complete_login(bot, ev, ready)
