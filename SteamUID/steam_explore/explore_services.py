"""探索队列命令实现：单账号执行、自动探索订阅开关与每日定时任务。"""

import asyncio
from dataclasses import dataclass
from collections.abc import Sequence

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..steam_config import SteamConfig
from ..utils.api.store import generate_discovery_queue, clear_discovery_queue_app
from ..utils.helper.bind import get_binds
from ..utils.helper.config import hide_id, store_base
from ..utils.helper.auth_token import renew_access_token
from ..utils.database.model_auth import SteamAuth
from ..utils.database.model_bind import SteamBind
from ..utils.helper.store_session import StoreSession, make_store_session, has_store_credentials

_TAG = "[Steam·探索队列]"
_PREFIX = "[Steam]"
TASK_NAME = "订阅Steam自动探索队列"

# Steam 对连续清队列有频率限制，逐个清除之间留一点间隔
_CLEAR_INTERVAL = 0.3

_NOT_LOGGED_IN = "未检测到该账号的登录授权，请先发送 steam登录 完成网页授权"
_AUTH_EXPIRED = "Steam 登录授权已失效，请重新发送 steam登录 后再试"
_NETWORK_ERROR = "网络异常，请稍后重试"
_PARSE_ERROR = "Steam 返回数据异常，请稍后重试"
_UNKNOWN_ERROR = "执行异常，请稍后重试"

# 正在执行的账号，避免手动命令与自动任务对同一账号重复执行
_running: set[str] = set()


@dataclass(frozen=True)
class QueueOutcome:
    """单个账号的探索结果；ok 为 False 时 reason 是对用户可见的原因。"""

    steamid64: str
    name: str
    ok: bool
    cleared: int
    reason: str


def _display_name(account: SteamAuth | None, steamid64: str) -> str:
    """账号展示名：登录时记录的昵称为空时回落 steamid64。"""
    if account is not None and account.account_name:
        return account.account_name
    return steamid64


def _failure_reason(status: int) -> str:
    """非授权类 HTTP 失败的提示文案。"""
    if status == 429:
        return "Steam 请求过于频繁，请稍后再试"
    return f"Steam 接口返回异常状态码 {status}"


def _unique(steamids: Sequence[str]) -> list[str]:
    """按出现顺序去重，保证执行与报告顺序稳定。"""
    result: list[str] = []
    for steamid64 in steamids:
        if steamid64 not in result:
            result.append(steamid64)
    return result


async def _run_rounds(session: StoreSession, *, rounds: int, interval: float) -> int:
    """跑完全部轮次并返回清空总数；凭据失效抛给上层判定。"""
    cleared = 0
    for index in range(rounds):
        if index:
            await asyncio.sleep(interval)
        appids = await generate_discovery_queue(session.client, session_id=session.session_id, base_url=store_base())
        for appid in appids:
            await clear_discovery_queue_app(session.client, appid, session_id=session.session_id, base_url=store_base())
            await asyncio.sleep(_CLEAR_INTERVAL)
        cleared += len(appids)
    return cleared


async def _attempt_queue(account: SteamAuth, *, rounds: int, interval: float) -> QueueOutcome | None:
    """执行一次完整探索；返回 None 表示凭据失效，交由上层刷新后重试。"""
    name = _display_name(account, account.steamid64)
    session = make_store_session(account)
    try:
        async with session.client:
            cleared = await _run_rounds(session, rounds=rounds, interval=interval)
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status in (401, 403):
            return None
        logger.warning(f"{_TAG} 账号 {account.steamid64} 探索失败 HTTP {status}")
        return QueueOutcome(steamid64=account.steamid64, name=name, ok=False, cleared=0, reason=_failure_reason(status))
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 账号 {account.steamid64} 探索网络异常: {type(error).__name__}")
        return QueueOutcome(steamid64=account.steamid64, name=name, ok=False, cleared=0, reason=_NETWORK_ERROR)
    return QueueOutcome(steamid64=account.steamid64, name=name, ok=True, cleared=cleared, reason="")


async def _explore_account(steamid64: str, *, rounds: int, interval: float) -> QueueOutcome:
    """执行单个账号的探索队列；凭据失效时刷新一次再重试。"""
    account = await SteamAuth.get_account(steamid64)
    name = _display_name(account, steamid64)
    if account is None or not has_store_credentials(account):
        return QueueOutcome(steamid64=steamid64, name=name, ok=False, cleared=0, reason=_NOT_LOGGED_IN)

    outcome = await _attempt_queue(account, rounds=rounds, interval=interval)
    if outcome is not None:
        return outcome
    if await renew_access_token(steamid64) is None:
        return QueueOutcome(steamid64=steamid64, name=name, ok=False, cleared=0, reason=_AUTH_EXPIRED)

    renewed = await SteamAuth.get_account(steamid64)
    if renewed is None or not has_store_credentials(renewed):
        return QueueOutcome(steamid64=steamid64, name=name, ok=False, cleared=0, reason=_AUTH_EXPIRED)
    retry = await _attempt_queue(renewed, rounds=rounds, interval=interval)
    if retry is None:
        return QueueOutcome(steamid64=steamid64, name=name, ok=False, cleared=0, reason=_AUTH_EXPIRED)
    return retry


async def _run_account(steamid64: str) -> QueueOutcome:
    """单账号执行入口：取配置并收口异常，失败以结果返回而不是抛出。"""
    rounds = SteamConfig.get_config("QueueRounds").data
    interval = float(SteamConfig.get_config("QueueInterval").data)
    try:
        return await _explore_account(steamid64, rounds=rounds, interval=interval)
    except ValueError as error:
        logger.warning(f"{_TAG} 账号 {steamid64} 探索响应解析失败: {error}")
        return QueueOutcome(steamid64=steamid64, name=steamid64, ok=False, cleared=0, reason=_PARSE_ERROR)
    except Exception as error:
        logger.exception(f"{_TAG} 账号 {steamid64} 探索异常: {type(error).__name__}")
        return QueueOutcome(steamid64=steamid64, name=steamid64, ok=False, cleared=0, reason=_UNKNOWN_ERROR)


async def _run_batch(steamids: Sequence[str]) -> list[QueueOutcome]:
    """顺序执行一批账号并逐个占用运行标记，返回各自的执行结果。"""
    outcomes: list[QueueOutcome] = []
    for steamid64 in steamids:
        _running.add(steamid64)
        try:
            outcomes.append(await _run_account(steamid64))
        finally:
            _running.discard(steamid64)
    return outcomes


def _report_text(outcomes: Sequence[QueueOutcome]) -> str:
    """聚合报告：成功账号数与清空总数，失败逐个列出原因。"""
    done = [outcome for outcome in outcomes if outcome.ok]
    failed = [outcome for outcome in outcomes if not outcome.ok]
    lines = [
        f"{_PREFIX} 探索队列结果",
        f"- 成功：{len(done)} 个账号，共清空 {sum(outcome.cleared for outcome in done)} 个游戏",
    ]
    if failed:
        lines.append(f"- 失败：{len(failed)} 个账号")
        lines.extend(
            f"[{index}] {hide_id(outcome.name)}({hide_id(outcome.steamid64)}) - {outcome.reason}"
            for index, outcome in enumerate(failed, start=1)
        )
    return "\n".join(lines)


async def run_manual_queue(bot: Bot, ev: Event) -> None:
    """steam探索队列：立即对该会话内该用户绑定的全部账号执行探索队列。"""
    binds = await get_binds(ev, ev.user_id)
    steamids = _unique([bind.steamid64 for bind in binds if bind.steamid64])
    if not steamids:
        raise ValueError("请先绑定 steam 账号")

    pending = [steamid64 for steamid64 in steamids if steamid64 not in _running]
    if not pending:
        raise ValueError("名下账号已有探索队列任务在执行，请稍后再试")

    await bot.send("正在执行探索队列，请稍候......")
    outcomes = await _run_batch(pending)
    await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f"\n{_report_text(outcomes)}")])


async def _is_auto_enabled(ev: Event) -> bool:
    """该用户在当前会话是否已开启自动探索。"""
    rows = await gs_subscribe.get_subscribe(
        TASK_NAME,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
    )
    return bool(rows)


async def toggle_auto_queue(bot: Bot, ev: Event, enable: bool) -> None:
    """steam开启 / 关闭自动探索队列：为该用户写入 / 删除每日自动探索订阅。"""
    binds = await get_binds(ev, ev.user_id)
    if not binds:
        raise ValueError("请先绑定 steam 账号")

    if enable:
        await gs_subscribe.add_subscribe("single", TASK_NAME, ev)
        await bot.send("已开启自动探索队列，每日将按配置时间为你名下所有 Steam 账号执行探索")
        return
    if not await _is_auto_enabled(ev):
        await bot.send("未开启自动探索队列")
        return
    await gs_subscribe.delete_subscribe("single", TASK_NAME, ev)
    await bot.send("已关闭自动探索队列")


async def _session_steamids(sub: Subscribe) -> list[str]:
    """订阅所属会话内该用户绑定的全部账号；无绑定返回空表。"""
    binds = await SteamBind.get_binds_by_session(
        sub.user_id,
        sub.bot_id,
        sub.bot_self_id or "",
        sub.group_id or "",
    )
    return _unique([bind.steamid64 for bind in binds if bind.steamid64])


async def _send_result(sub: Subscribe, text: str, *, force_direct: bool = False) -> None:
    """推送一条报告；失败只记日志，不影响其它会话。"""
    try:
        await sub.send(text, force_direct=force_direct)
    except Exception as error:
        logger.warning(f"{_TAG} 推送结果失败 user={sub.user_id}: {type(error).__name__}")


async def _send_report(
    sub: Subscribe,
    steamids: Sequence[str],
    results: dict[str, QueueOutcome],
    *,
    force_direct: bool = False,
) -> None:
    """按账号列表汇总一份报告并推送；本轮未执行的账号不计入。"""
    outcomes = [results[steamid64] for steamid64 in steamids if steamid64 in results]
    if not outcomes:
        return
    await _send_result(sub, _report_text(outcomes), force_direct=force_direct)


async def _auto_queue_once() -> None:
    """执行全部待跑账号：群会话出一份群报告，开启者再收一份个人报告。"""
    rows = await gs_subscribe.get_subscribe(TASK_NAME)
    # 框架订阅接口无类型标注，这里立刻收窄为 Subscribe
    subs = [row for row in rows if isinstance(row, Subscribe)] if rows is not None else []

    group_subs: dict[tuple[str, str, str], Subscribe] = {}
    group_accounts: dict[tuple[str, str, str], list[str]] = {}
    user_subs: dict[tuple[str, str, str], Subscribe] = {}
    user_accounts: dict[tuple[str, str, str], list[str]] = {}
    for sub in subs:
        steamids = await _session_steamids(sub)
        if not steamids:
            logger.info(f"{_TAG} 用户 {sub.user_id} 在当前会话无绑定账号，跳过")
            continue
        if sub.user_type == "group" and sub.group_id:
            group_key = (sub.bot_id, sub.bot_self_id or "", sub.group_id)
            group_subs.setdefault(group_key, sub)
            group_accounts.setdefault(group_key, []).extend(steamids)
        user_key = (sub.bot_id, sub.bot_self_id or "", sub.user_id)
        user_subs.setdefault(user_key, sub)
        user_accounts.setdefault(user_key, []).extend(steamids)

    ordered = _unique([steamid64 for sids in user_accounts.values() for steamid64 in sids])
    pending = [steamid64 for steamid64 in ordered if steamid64 not in _running]
    if not pending:
        logger.info(f"{_TAG} 无待执行的账号，跳过本轮")
        return

    results = {outcome.steamid64: outcome for outcome in await _run_batch(pending)}

    if SteamConfig.get_config("QueuePushGroup").data:
        for group_key, group_sub in group_subs.items():
            await _send_report(group_sub, _unique(group_accounts[group_key]), results)
    if SteamConfig.get_config("QueuePushPrivate").data:
        for user_key, user_sub in user_subs.items():
            await _send_report(
                user_sub, _unique(user_accounts[user_key]), results, force_direct=bool(user_sub.group_id)
            )


async def run_auto_queue_job() -> None:
    """每日定时任务入口；异常在此收口，避免打断调度器。"""
    try:
        await _auto_queue_once()
    except Exception as error:
        logger.exception(f"{_TAG} 自动探索任务异常: {type(error).__name__}")
