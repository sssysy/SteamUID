"""CDKey 激活命令实现：仅私聊、二次确认与逐枚激活的结果汇报。"""

import asyncio
from dataclasses import dataclass
from collections.abc import Sequence

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.api.store import register_cdkey
from ..utils.api.models import RegisterCdKeyResponse
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.cdkey import RESULT_REASONS, split_cdkeys, normalize_cdkey
from ..utils.helper.config import hide_id, store_base
from ..utils.helper.auth_token import renew_access_token
from ..utils.database.model_auth import SteamAuth
from ..utils.helper.store_session import StoreSession, make_store_session, has_store_credentials

_TAG = "[Steam·CDKey激活]"
_PREFIX = "[Steam]"
_CONFIRM_TEXT = "steam确认激活"
_CONFIRM_TIMEOUT = 60.0
# Steam 对连续激活有限频，枚间留出安全间隔
_ACTIVATE_INTERVAL = 1.5

_NOT_DIRECT = "为防止 CDKey 泄露，请私聊机器人使用 steam激活"
_NO_BIND = "请先绑定 steam 账号并将其设为主账号"
_NOT_LOGGED_IN = "未检测到该账号的登录授权，请先发送 steam登录 完成网页授权"
_AUTH_EXPIRED = "Steam 登录授权已失效，请重新发送 steam登录 后再试"
_NETWORK_ERROR = "网络异常，请稍后重试"
_PARSE_ERROR = "Steam 返回数据异常，请稍后重试"
_UNKNOWN_GAME = "未知游戏"
_SKIPPED = "已跳过(触发限频)"

# 正在激活的账号，避免同一账号并发提交
_running: set[str] = set()


@dataclass(frozen=True)
class KeyOutcome:
    """单枚激活结果；rate_limited 为真表示触发限频，需熔断后续枚数。"""

    cdk: str
    ok: bool
    detail: str
    rate_limited: bool = False


def _name(account: SteamAuth, steamid64: str) -> str:
    """账号展示名；登录时记录的昵称为空时回落 steamid64。"""
    return account.account_name or hide_id(steamid64)


def _failure_reason(status: int) -> str:
    """非授权类 HTTP 失败的提示文案。"""
    if status == 429:
        return "Steam 请求过于频繁，请稍后再试"
    return f"Steam 接口返回异常状态码 {status}"


def _parse_cdkeys(text: str) -> list[str]:
    """解析输入的 CDKey 列表；任一枚非法即抛错中止整批，不做跳过。"""
    tokens = split_cdkeys(text)
    if not tokens:
        raise ValueError("未检测到 CDKey，用法：steam激活<CDKey>，多枚可用空格 / 逗号分隔")

    cdks: list[str] = []
    for index, token in enumerate(tokens, start=1):
        key = normalize_cdkey(token)
        if key is None:
            raise ValueError(f"第 {index} 枚 CDKey 格式有误：{token}\n请核对后再试，本次未提交任何激活")
        cdks.append(key)
    return cdks


def _confirm_message(cdks: Sequence[str], name: str, steamid64: str) -> str:
    """二次确认文本：回显解析后的 CDKey 与目标账号，供用户逐条核对。"""
    lines = "\n".join(f"[{index}] {cdk}" for index, cdk in enumerate(cdks, start=1))
    return (
        f"{_PREFIX} CDKey 激活确认\n"
        f"账号：{name} ({hide_id(steamid64)})\n"
        f"待激活 {len(cdks)} 枚：\n{lines}\n"
        f"确认无误请回复 {_CONFIRM_TEXT}，其它回复或 {int(_CONFIRM_TIMEOUT)} 秒内无操作将取消。"
    )


def _game_name(payload: RegisterCdKeyResponse) -> str:
    """取回执中的入库产品名；回执缺失时回落空串，由调用方展示占位。"""
    if "purchase_receipt_info" not in payload:
        return ""
    receipt = payload["purchase_receipt_info"]
    if "line_items" not in receipt or not receipt["line_items"]:
        return ""
    item = receipt["line_items"][0]
    if "line_item_description" not in item:
        return ""
    return item["line_item_description"]


def _pending(cdks: Sequence[str], detail: str) -> list[KeyOutcome]:
    """把未执行的剩余 CDKey 统一标记成同一种原因。"""
    return [KeyOutcome(cdk=cdk, ok=False, detail=detail) for cdk in cdks]


async def _activate_one(session: StoreSession, cdk: str) -> KeyOutcome:
    """激活一枚并翻译结果码；HTTP 异常原样抛出，由上层边界判定。"""
    payload = await register_cdkey(session.client, cdk, base_url=store_base())
    if "purchase_result_details" not in payload:
        return KeyOutcome(cdk=cdk, ok=False, detail=_PARSE_ERROR)

    code = payload["purchase_result_details"]
    if code == 0:
        return KeyOutcome(cdk=cdk, ok=True, detail=_game_name(payload) or _UNKNOWN_GAME)
    detail = RESULT_REASONS[code] if code in RESULT_REASONS else f"激活失败(代码: {code})"
    return KeyOutcome(cdk=cdk, ok=False, detail=detail, rate_limited=code == 53)


async def _run_keys(account: SteamAuth, cdks: Sequence[str]) -> list[KeyOutcome] | None:
    """逐枚激活；返回 None 表示首枚即凭据失效，交由上层换新后重跑整批。"""
    session = make_store_session(account)
    outcomes: list[KeyOutcome] = []
    try:
        for index, cdk in enumerate(cdks):
            if index:
                await asyncio.sleep(_ACTIVATE_INTERVAL)
            try:
                outcome = await _activate_one(session, cdk)
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if status in (401, 403):
                    if not outcomes:
                        return None
                    # 已提交的码不能重跑，剩余统一按授权失效标记
                    outcomes.append(KeyOutcome(cdk=cdk, ok=False, detail=_AUTH_EXPIRED))
                    outcomes.extend(_pending(cdks[index + 1 :], _AUTH_EXPIRED))
                    return outcomes
                logger.warning(f"{_TAG} 账号 {account.steamid64} 激活失败 HTTP {status}")
                outcome = KeyOutcome(cdk=cdk, ok=False, detail=_failure_reason(status))
            except httpx.HTTPError as error:
                logger.warning(f"{_TAG} 账号 {account.steamid64} 激活网络异常: {type(error).__name__}")
                outcome = KeyOutcome(cdk=cdk, ok=False, detail=_NETWORK_ERROR)

            outcomes.append(outcome)
            if outcome.rate_limited:
                logger.warning(f"{_TAG} 账号 {account.steamid64} 触发 53 限频，已熔断后续激活")
                outcomes.extend(_pending(cdks[index + 1 :], _SKIPPED))
                break
        return outcomes
    finally:
        await session.client.aclose()


async def _activate_account(account: SteamAuth, cdks: Sequence[str]) -> list[KeyOutcome]:
    """单账号激活：仅首枚就凭据失效时换新重试，避免重跑已提交的码。"""
    outcomes = await _run_keys(account, cdks)
    if outcomes is not None:
        return outcomes

    if await renew_access_token(account.steamid64) is None:
        raise ValueError(_AUTH_EXPIRED)
    renewed = await SteamAuth.get_account(account.steamid64)
    if renewed is None or not has_store_credentials(renewed):
        raise ValueError(_AUTH_EXPIRED)

    retry = await _run_keys(renewed, cdks)
    if retry is None:
        raise ValueError(_AUTH_EXPIRED)
    return retry


def _report_text(outcomes: Sequence[KeyOutcome], name: str, steamid64: str) -> str:
    """汇总报告：成功带入库游戏名，失败逐条列出原因。"""
    done = [outcome for outcome in outcomes if outcome.ok]
    failed = [outcome for outcome in outcomes if not outcome.ok]
    lines = [
        f"{_PREFIX} CDKey 激活结果",
        f"账号：{name} ({hide_id(steamid64)})",
        f"成功 {len(done)} 枚，失败 {len(failed)} 枚",
    ]
    lines.extend(f"[{index}] {outcome.detail} | {outcome.cdk}" for index, outcome in enumerate(done, start=1))
    lines.extend(f"[{index}] {outcome.cdk} | {outcome.detail}" for index, outcome in enumerate(failed, start=1))
    return "\n".join(lines)


async def activate_cdkeys(bot: Bot, ev: Event) -> None:
    """steam激活<CDKey>：仅私聊，对当前主账号逐枚激活，提交前二次确认。"""
    if ev.user_type != "direct":
        raise ValueError(_NOT_DIRECT)

    steamid64 = await get_main_steamid64(ev, ev.user_id)
    if steamid64 is None:
        raise ValueError(_NO_BIND)

    account = await SteamAuth.get_account(steamid64)
    if account is None or not has_store_credentials(account):
        raise ValueError(_NOT_LOGGED_IN)

    cdks = _parse_cdkeys(ev.text)
    name = _name(account, steamid64)

    if steamid64 in _running:
        raise ValueError("该账号已有激活任务在执行，请稍后再试")
    _running.add(steamid64)
    try:
        reply = await bot.receive_resp(_confirm_message(cdks, name, steamid64), timeout=_CONFIRM_TIMEOUT)
        if reply is None:
            await bot.send(f"{_PREFIX} 等待确认超时，已取消本次激活。")
            return
        if reply.text.strip() != _CONFIRM_TEXT:
            await bot.send(f"{_PREFIX} 已取消本次激活。")
            return

        await bot.send(f"{_PREFIX} 开始激活 {len(cdks)} 枚 CDKey，请稍候......")
        outcomes = await _activate_account(account, cdks)
        await bot.send(_report_text(outcomes, name, steamid64))
        logger.info(f"{_TAG} 账号 {steamid64} 激活结束，共提交 {len(cdks)} 枚")
    finally:
        _running.discard(steamid64)
