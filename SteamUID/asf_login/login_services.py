"""ASF 扫码登录流程：建 bot、写默认隐身与暂停、扫码、重命名为 steamid。"""

import time
import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment

from ..utils.asf.api import (
    get_bots,
    stop_bot,
    pause_bot,
    start_bot,
    rename_bot,
    send_input,
    update_bot_config,
)
from ..utils.asf.models import AsfBot, AsfEOlineStatus, AsfEUserInputType, AsfEFarmingPreferences
from ..utils.helper.asf import asf_endpoint, asf_settings
from ..utils.helper.bind import session_ids
from ..utils.render.pil.render_qr import render_qr_png

_TAG = "[Steam·ASF登录]"
_CONFIRM_TIMEOUT_SECONDS = 180.0
_LOGIN_TIMEOUT_SECONDS = 180.0
_POLL_INTERVAL_SECONDS = 2.0
_CONFIRM_TEXT = "确认继续登录"
_QR_INPUT = AsfEUserInputType.QR_CODE_LOGIN

_RISK_NOTICE = (
    "【注意】将通过 ASF 登录该 Steam 账号，账号会保持登录在 ASF 上。\n"
    "登录后默认设置为隐身，并默认暂停挂卡。\n"
    "确认继续登录，请在 3 分钟内发送【确认继续登录】，否则静默或发送任意文本取消登录"
)


def _at_user(ev: Event) -> Message:
    return MessageSegment.at(ev.user_id)


async def _notify(bot: Bot, ev: Event, text: str) -> None:
    await bot.send([_at_user(ev), MessageSegment.text(f" [Steam] {text}")])


async def _cancel_login(bot: Bot, ev: Event) -> None:
    await bot.send([_at_user(ev), MessageSegment.text(" 已取消 ASF 登录！")])


def _bot_name(ev: Event) -> str:
    """会话内唯一命名：群号_用户号；私聊用 0_用户号。"""
    _, _, group_id = session_ids(ev)
    scope = group_id if group_id else "0"
    return f"{scope}_{ev.user_id}"


def _steamid_of(bot_state: AsfBot) -> str:
    raw = bot_state["SteamID"]
    return str(raw)


async def _wait_for_confirm(bot: Bot, ev: Event) -> bool:
    resp = await bot.receive_resp(_RISK_NOTICE, timeout=_CONFIRM_TIMEOUT_SECONDS)
    return resp is not None and resp.text.strip() == _CONFIRM_TEXT


async def _create_or_get_bot(bot_name: str) -> AsfBot:
    """bot 不存在时写最小配置，ASF 会自动发现并注册。"""
    endpoint = asf_endpoint()
    bots = await get_bots(endpoint, bot_name)
    if bot_name in bots:
        return bots[bot_name]

    await update_bot_config(
        endpoint,
        bot_name,
        {
            "Enabled": True,
            "OnlineStatus": int(AsfEOlineStatus.INVISIBLE),
            "FarmingPreferences": int(AsfEFarmingPreferences.FARMING_PAUSED_BY_DEFAULT),
        },
    )
    deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        bots = await get_bots(endpoint, bot_name)
        if bot_name in bots:
            return bots[bot_name]
    raise ValueError("ASF 未能创建 bot，请检查 ASF 日志")


async def _ensure_safe_config(bot_name: str, state: AsfBot) -> None:
    """合并而不是整份覆盖：只改隐身与暂停位，保留用户其它配置。"""
    endpoint = asf_endpoint()
    config: dict[str, object] = dict(state["BotConfig"])
    farming = int(AsfEFarmingPreferences.NONE)
    if "FarmingPreferences" in config:
        current_farming = config["FarmingPreferences"]
        if not isinstance(current_farming, int):
            raise ValueError("ASF BotConfig 的 FarmingPreferences 类型异常")
        farming = current_farming
    config["OnlineStatus"] = int(AsfEOlineStatus.INVISIBLE)
    config["FarmingPreferences"] = farming | int(AsfEFarmingPreferences.FARMING_PAUSED_BY_DEFAULT)
    await update_bot_config(endpoint, bot_name, config)


async def _wait_for_qr(
    bot_name: str,
    bot: Bot,
    ev: Event,
) -> str:
    """等待 ASF 请求扫码选择；首次拿到二维码后返回链接。"""
    endpoint = asf_endpoint()
    deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
    last_url = ""
    while time.monotonic() < deadline:
        bots = await get_bots(endpoint, bot_name)
        if bot_name not in bots:
            raise ValueError("ASF 中已找不到该 bot，请检查 ASF 日志")
        state = bots[bot_name]
        if state["IsConnectedAndLoggedOn"]:
            raise ValueError("该 ASF 账号已登录，无需重复扫码")

        url = state["QrChallengeURL"]
        if url is None:
            required = state["RequiredInput"]
            if required == int(_QR_INPUT):
                await send_input(endpoint, bot_name, _QR_INPUT, "Y")
            elif required in (int(AsfEUserInputType.LOGIN), int(AsfEUserInputType.PASSWORD)):
                raise ValueError("ASF 正在等待账号密码，无法进入扫码流程；请检查 ASF 是否处于无头模式")
            else:
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            continue

        if url != last_url:
            last_url = url
            image = await render_qr_png(url)
            await bot.send(MessageSegment.image(image))
            await _notify(
                bot,
                ev,
                "请使用 Steam App 扫描上方二维码登录；二维码刷新时会自动重发。",
            )
            return url

        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    raise ValueError("ASF 登录超时，请重新发起")


async def _finish_login(bot_name: str, bot: Bot, ev: Event) -> None:
    endpoint = asf_endpoint()
    deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        bots = await get_bots(endpoint, bot_name)
        if bot_name not in bots:
            raise ValueError("ASF 中已找不到该 bot，请检查 ASF 日志")
        state = bots[bot_name]
        if state["IsConnectedAndLoggedOn"]:
            steamid = _steamid_of(state)
            if steamid and steamid != bot_name:
                await pause_bot(endpoint, bot_name)
                await stop_bot(endpoint, bot_name)
                await _wait_stopped(bot_name)
                await rename_bot(endpoint, bot_name, steamid)
                await _wait_renamed(steamid)
                await start_bot(endpoint, steamid)
                await _wait_logged_on(steamid)
            else:
                await pause_bot(endpoint, bot_name)
            await _notify(bot, ev, f"ASF 登录成功，账号已保存为 {steamid}")
            logger.info(f"{_TAG} bot {bot_name} 登录成功，steamid={steamid}")
            return
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise ValueError("ASF 登录未完成，请稍后在 ASF 中查看状态")


async def _wait_stopped(bot_name: str) -> None:
    """重命名前确认 bot 已停止，避免 ASF 在运行态迁移数据库。"""
    endpoint = asf_endpoint()
    deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        bots = await get_bots(endpoint, bot_name)
        if bot_name not in bots:
            raise ValueError("ASF 中已找不到该 bot，请检查 ASF 日志")
        if not bots[bot_name]["IsConnectedAndLoggedOn"]:
            return
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise ValueError("ASF bot 停止超时，无法重命名")


async def _wait_renamed(new_name: str) -> None:
    """确认重命名后的 bot 已被 ASF 重新注册。"""
    endpoint = asf_endpoint()
    deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        bots = await get_bots(endpoint, new_name)
        if new_name in bots:
            return
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise ValueError("ASF 重命名后未找到新 bot")


async def _wait_logged_on(bot_name: str) -> None:
    """重命名后重启 bot，确认登录态仍在。"""
    endpoint = asf_endpoint()
    deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        bots = await get_bots(endpoint, bot_name)
        if bot_name in bots and bots[bot_name]["IsConnectedAndLoggedOn"]:
            return
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise ValueError("ASF 重命名后登录态失效，请重新登录")


async def start_asf_login(bot: Bot, ev: Event) -> None:
    settings = asf_settings()
    if not settings.enabled:
        raise ValueError("ASF 相关功能未启用")
    if not await _wait_for_confirm(bot, ev):
        await _cancel_login(bot, ev)
        return

    bot_name = _bot_name(ev)
    endpoint = asf_endpoint()
    state = await _create_or_get_bot(bot_name)
    if state["IsConnectedAndLoggedOn"]:
        steamid = _steamid_of(state)
        await _notify(bot, ev, f"该 ASF 账号已登录：{steamid}")
        return
    if state["HasMobileAuthenticator"]:
        raise ValueError("该 ASF 账号已启用 ASF 2FA，无法使用扫码登录")

    await _ensure_safe_config(bot_name, state)
    await start_bot(endpoint, bot_name)
    await _wait_for_qr(bot_name, bot, ev)
    await _finish_login(bot_name, bot, ev)
