from __future__ import annotations

import asyncio
import json
from typing import Any, Optional
import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe

from ..SteamConfig import SteamConfig
from ..utils.Api import (
    SteamStoreAuthExpiredError,
    clear_discovery_queue_app,
    generate_discovery_queue,
    make_async_client,
)
from ..utils.database.models import SteamBind, SteamNextAccount
from ..utils.helpers.credentials import apply_cookies
from ..utils.helpers.profile import get_account_display_name

SUBSCRIBE_TASK_NAME = "订阅Steam自动探索队列"

# Store 会话 Cookie 只写在商店域名上
STORE_DOMAIN = "store.steampowered.com"

# 正在执行探索队列的 steamid 集合（用于并发重入保护）
_running_queue_steamids: set[str] = set()


def _build_store_client(acc: SteamNextAccount) -> httpx.AsyncClient:
    """构建携带完整登录凭据的 Store 会话客户端"""
    client = make_async_client(
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        timeout=15,
    )

    cookies: dict[str, str] = {}
    if acc.cookies_json:
        try:
            cookies_dict = json.loads(acc.cookies_json)
            if isinstance(cookies_dict, dict):
                cookies.update({str(k): str(v) for k, v in cookies_dict.items()})
        except Exception as e:
            logger.warning(f"[SteamDiscoveryQueue] 账号 {acc.steamid64} 解析 Cookies 异常: {e}")

    if acc.session_id:
        cookies["sessionid"] = str(acc.session_id)
    if acc.steamid64 and acc.access_token:
        cookies["steamLoginSecure"] = f"{acc.steamid64}||{acc.access_token}"

    apply_cookies(client, cookies, (STORE_DOMAIN,))

    return client


async def _fetch_queue(client: httpx.AsyncClient, store_base_url: str, session_id: str) -> list[int]:
    return await generate_discovery_queue(client, store_base_url, session_id)


async def _clear_app(client: httpx.AsyncClient, store_base_url: str, session_id: str, appid: int):
    await clear_discovery_queue_app(client, store_base_url, session_id, appid)


def format_queue_result(
    success_count: int,
    failed_count: int,
    failed_list: list[tuple[str, str, str]],
) -> str:
    """按要求组装任务结果文本"""
    msg_lines = [
        "[Steam 探索队列任务]",
        f"- 成功：{success_count} 个账号",
        f"- 失败：{failed_count} 个账号",
    ]

    if failed_list:
        msg_lines.append("- 失败列表(如果有的话)：")
        for idx, (name, sid, reason) in enumerate(failed_list, start=1):
            msg_lines.append(f"[{idx}] {name} ({sid}) - {reason}")

    return "\n".join(msg_lines)


async def execute_queue_for_steamids(
    steamids: list[str],
) -> dict[str, tuple[bool, str, str]]:
    """
    对一组 Steam 账号执行探索队列
    返回结果字典: steamid64 -> (is_success, steam_name, fail_reason)
    """
    rounds_per_account = int(SteamConfig.get_config("AutoQueueCount").data)
    interval_seconds = float(SteamConfig.get_config("AutoQueueInterval").data)
    store_base_url = SteamConfig.get_config("storeBaseURL").data.strip()

    results: dict[str, tuple[bool, str, str]] = {}
    accounts_to_run: list[tuple[str, str, SteamNextAccount]] = []

    for sid in steamids:
        steam_name = await get_account_display_name(sid)
        acc = await SteamNextAccount.get_account(sid)
        if not acc or not acc.access_token or not acc.session_id:
            results[sid] = (False, steam_name, "仅绑定未登录")
        else:
            accounts_to_run.append((steam_name, sid, acc))

    for acc_idx, (steam_name, sid, acc) in enumerate(accounts_to_run):
        client = _build_store_client(acc)
        account_failed = False
        fail_reason = ""

        try:
            for r in range(rounds_per_account):
                logger.info(
                    f"[SteamDiscoveryQueue] 开始执行账号 {steam_name}({sid}) "
                    f"第 {r + 1}/{rounds_per_account} 轮探索队列..."
                )
                try:
                    queue = await _fetch_queue(client, store_base_url, acc.session_id)
                    if queue:
                        for appid in queue:
                            await _clear_app(client, store_base_url, acc.session_id, appid)
                            await asyncio.sleep(0.3)
                    logger.info(
                        f"[SteamDiscoveryQueue] 账号 {steam_name}({sid}) "
                        f"第 {r + 1} 轮探索完成（已清空 {len(queue)} 个游戏）"
                    )
                except SteamStoreAuthExpiredError as e:
                    account_failed = True
                    fail_reason = str(e)
                    logger.warning(f"[SteamDiscoveryQueue] 账号 {steam_name}({sid}) 凭证已失效: {e}")
                    break
                except Exception as e:
                    account_failed = True
                    fail_reason = f"接口异常: {e}"
                    logger.exception(f"[SteamDiscoveryQueue] 账号 {steam_name}({sid}) 探索队列异常: {e}")
                    break

                is_last_round_overall = (acc_idx == len(accounts_to_run) - 1) and (
                    r == rounds_per_account - 1
                )
                if not is_last_round_overall and interval_seconds > 0:
                    logger.info(f"[SteamDiscoveryQueue] 等待探索间隔 {interval_seconds} 秒...")
                    await asyncio.sleep(interval_seconds)
        finally:
            await client.aclose()

        if account_failed:
            results[sid] = (False, steam_name, fail_reason)
        else:
            results[sid] = (True, steam_name, "")

    return results


async def handle_user_discovery_queue(bot: Bot, ev: Event):
    """处理用户手动触发的探索队列指令"""
    await bot.send("Steam 探索队列开始工作......")

    binds = await SteamBind.get_binds_by_user(
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
        group_id=ev.group_id,
    )

    seen_steamids = set()
    bound_steamids: list[str] = []
    for b in binds:
        if b.steamid64 and b.steamid64 not in seen_steamids:
            seen_steamids.add(b.steamid64)
            bound_steamids.append(b.steamid64)

    if not bound_steamids:
        await bot.send("未检测到绑定的 Steam 账号，请先使用【steam绑定】进行绑定！")
        return

    if any(sid in _running_queue_steamids for sid in bound_steamids):
        await bot.send("当前账号已有探索队列任务正在运行，请稍后再试！")
        return

    _running_queue_steamids.update(bound_steamids)
    try:
        results = await execute_queue_for_steamids(bound_steamids)
    finally:
        _running_queue_steamids.difference_update(bound_steamids)

    success_count = 0
    failed_count = 0
    failed_list: list[tuple[str, str, str]] = []
    for sid in bound_steamids:
        res = results.get(sid)
        if res:
            is_succ, name, reason = res
            if is_succ:
                success_count += 1
            else:
                failed_count += 1
                failed_list.append((name, sid, reason))

    reply_content = "\n" + format_queue_result(success_count, failed_count, failed_list)
    send_msg = [
        MessageSegment.at(ev.user_id),
        MessageSegment.text(reply_content),
    ]
    await bot.send(send_msg)


async def handle_switch_auto_queue(bot: Bot, ev: Event, enabled: bool):
    """处理用户开启/关闭自动探索队列命令"""
    if enabled:
        binds = await SteamBind.get_binds_by_user_id(ev.bot_id, ev.user_id)
        if not binds:
            binds = await SteamBind.get_binds_by_user(
                ev.bot_id, ev.user_id, ev.user_type, ev.group_id
            )
        if not binds:
            await bot.send("未检测到绑定的 Steam 账号，请先使用【steam绑定】进行绑定！")
            return
        await gs_subscribe.add_subscribe("single", SUBSCRIBE_TASK_NAME, ev)
        await bot.send("已开启自动探索队列！每日将在指定时间为您名下的所有 Steam 账号自动执行探索。")
    else:
        await gs_subscribe.delete_subscribe("single", SUBSCRIBE_TASK_NAME, ev)
        await bot.send("已关闭自动探索队列！")


async def run_auto_discovery_queue_job():
    """定时任务：执行全量自动探索队列并按渠道分发结果"""
    logger.info("[SteamDiscoveryQueue] 开始执行每日自动探索队列任务...")
    datas = await gs_subscribe.get_subscribe(SUBSCRIBE_TASK_NAME)
    if not datas:
        logger.info("[SteamDiscoveryQueue] 当前无任何自动探索队列订阅，跳过执行。")
        return

    push_group = SteamConfig.get_config("QueuePushGroup").data
    push_private = SteamConfig.get_config("QueuePushPrivate").data

    user_accounts: dict[tuple[str, str], list[str]] = {}
    user_subs: dict[tuple[str, str], Any] = {}
    group_accounts: dict[tuple[str, str], list[str]] = {}
    group_subs: dict[tuple[str, str], Any] = {}

    all_steamids_set = set()
    all_steamids_ordered: list[str] = []

    for sub in datas:
        u_key = (sub.bot_id, sub.user_id)
        if u_key not in user_subs:
            user_subs[u_key] = sub
            binds = await SteamBind.get_binds_by_user_id(sub.bot_id, sub.user_id)
            if not binds:
                binds = await SteamBind.get_binds_by_user(
                    sub.bot_id, sub.user_id, sub.user_type, sub.group_id
                )
            sids: list[str] = []
            for b in binds:
                if b.steamid64 and b.steamid64 not in sids:
                    sids.append(b.steamid64)
                    if b.steamid64 not in all_steamids_set:
                        all_steamids_set.add(b.steamid64)
                        all_steamids_ordered.append(b.steamid64)
            user_accounts[u_key] = sids

        if sub.user_type == "group" and sub.group_id:
            g_key = (sub.bot_id, sub.group_id)
            if g_key not in group_subs:
                group_subs[g_key] = sub
                group_accounts[g_key] = []
            for sid in user_accounts.get(u_key, []):
                if sid not in group_accounts[g_key]:
                    group_accounts[g_key].append(sid)

    if not all_steamids_ordered:
        logger.info("[SteamDiscoveryQueue] 订阅用户未绑定任何有效 Steam 账号，无需执行探索。")
        return

    logger.info(
        f"[SteamDiscoveryQueue] 共有 {len(all_steamids_ordered)} 个独立 Steam 账号待执行探索..."
    )
    steamids_to_run = [sid for sid in all_steamids_ordered if sid not in _running_queue_steamids]
    if not steamids_to_run:
        logger.info("[SteamDiscoveryQueue] 所有待执行账号均已有任务运行中，跳过本次自动探索。")
        return

    _running_queue_steamids.update(steamids_to_run)
    try:
        results = await execute_queue_for_steamids(steamids_to_run)
    finally:
        _running_queue_steamids.difference_update(steamids_to_run)

    # 1. 群聊推送
    if push_group:
        for g_key, sub in group_subs.items():
            sids = group_accounts.get(g_key, [])
            if not sids:
                continue
            success_count = 0
            failed_count = 0
            failed_list: list[tuple[str, str, str]] = []
            for sid in sids:
                res = results.get(sid)
                if res:
                    is_succ, name, reason = res
                    if is_succ:
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_list.append((name, sid, reason))
            msg = format_queue_result(success_count, failed_count, failed_list)
            try:
                await sub.send(msg)
            except Exception as e:
                logger.debug(
                    f"[SteamDiscoveryQueue] 向群 {sub.group_id} 推送探索结果失败: {e}"
                )

    # 2. 私聊推送
    if push_private:
        for u_key, sub in user_subs.items():
            sids = user_accounts.get(u_key, [])
            if not sids:
                continue
            success_count = 0
            failed_count = 0
            failed_list: list[tuple[str, str, str]] = []
            for sid in sids:
                res = results.get(sid)
                if res:
                    is_succ, name, reason = res
                    if is_succ:
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_list.append((name, sid, reason))
            msg = format_queue_result(success_count, failed_count, failed_list)
            try:
                await sub.send(msg, force_direct=True)
            except Exception as e:
                logger.debug(
                    f"[SteamDiscoveryQueue] 向用户 {sub.user_id} 私聊推送探索结果失败: {e}"
                )
