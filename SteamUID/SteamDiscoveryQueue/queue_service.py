# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional
import requests

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe

from ..SteamConfig import SteamConfig
from ..utils.api import get_user_Summaries
from ..utils.database.models import SteamBind, SteamIDInfo, SteamNextAccount

SUBSCRIBE_TASK_NAME = "订阅Steam自动探索队列"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)


class SteamAuthExpiredError(Exception):
    """Steam 登录凭据失效"""
    pass


def _build_store_session(acc: SteamNextAccount) -> requests.Session:
    """构建携带完整登录凭据的 Store 会话"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    # 设置代理
    try:
        proxy = SteamConfig.get_config("HttpProxy").data.strip()
        if proxy:
            session.proxies.update({"http": proxy, "https": proxy})
    except Exception:
        pass

    # 载入 cookies
    if acc.cookies_json:
        try:
            cookies_dict = json.loads(acc.cookies_json)
            if isinstance(cookies_dict, dict):
                for k, v in cookies_dict.items():
                    session.cookies.set(k, str(v), domain="store.steampowered.com")
        except Exception as e:
            logger.warning(f"[SteamDiscoveryQueue] 账号 {acc.steamid64} 解析 Cookies 异常: {e}")

    # 显式覆盖核心身份 Cookie
    if acc.session_id:
        session.cookies.set("sessionid", acc.session_id, domain="store.steampowered.com")
    if acc.steamid64 and acc.access_token:
        session.cookies.set(
            "steamLoginSecure",
            f"{acc.steamid64}||{acc.access_token}",
            domain="store.steampowered.com",
            secure=True,
        )

    return session


def _fetch_queue_sync(session: requests.Session, store_base_url: str, session_id: str) -> list[int]:
    """同步请求生成/获取新探索队列"""
    gen_url = f"{store_base_url.rstrip('/')}/explore/generatenewdiscoveryqueue"
    headers = {
        "Origin": store_base_url,
        "Referer": f"{store_base_url.rstrip('/')}/explore/",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = session.post(
        gen_url,
        data={"sessionid": session_id, "queuetype": 0},
        headers=headers,
        timeout=15,
    )
    if resp.status_code in (401, 403):
        raise SteamAuthExpiredError("登录凭证已失效，请重新登录")
    if resp.status_code != 200:
        raise Exception(f"生成探索队列异常 (HTTP {resp.status_code})")

    try:
        data = resp.json()
    except Exception:
        if "login" in resp.url or "login" in resp.text:
            raise SteamAuthExpiredError("登录凭证已失效，请重新登录")
        raise Exception("接口返回非有效 JSON 数据")

    queue = data.get("queue", [])
    if not isinstance(queue, list):
        return []
    return [int(x) for x in queue if str(x).isdigit()]


def _clear_app_sync(session: requests.Session, store_base_url: str, session_id: str, appid: int):
    """同步提交清除单个队列游戏"""
    app_url = f"{store_base_url.rstrip('/')}/app/{appid}"
    headers = {
        "Origin": store_base_url,
        "Referer": app_url,
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = session.post(
        app_url,
        data={
            "sessionid": session_id,
            "appid_to_clear_from_queue": appid,
        },
        headers=headers,
        timeout=10,
    )
    if resp.status_code in (401, 403):
        raise SteamAuthExpiredError("登录凭证已失效，请重新登录")


async def get_steam_nickname(steamid64: str) -> str:
    """获取 Steam 用户昵称"""
    try:
        user_info_raw = await SteamIDInfo.get_steamuserinfo(steamid64)
        if user_info_raw:
            info = json.loads(user_info_raw)
            if isinstance(info, dict) and info.get("personaname"):
                return info["personaname"]
    except Exception:
        pass

    try:
        sid_info = await get_user_Summaries(steamid64)
        if sid_info and isinstance(sid_info, list) and sid_info[0].get("personaname"):
            return sid_info[0]["personaname"]
    except Exception:
        pass

    try:
        acc = await SteamNextAccount.get_account(steamid64)
        if acc and acc.account_name:
            return acc.account_name
    except Exception:
        pass

    return "未知用户"


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
    try:
        rounds_config = SteamConfig.get_config("AutoQueueCount").data
        rounds_per_account = int(rounds_config) if rounds_config else 3
    except Exception:
        rounds_per_account = 3

    try:
        interval_config = SteamConfig.get_config("AutoQueueInterval").data
        interval_seconds = float(interval_config) if interval_config else 15.0
    except Exception:
        interval_seconds = 15.0

    try:
        store_base = SteamConfig.get_config("storeBaseURL").data.strip()
    except Exception:
        store_base = ""
    store_base_url = store_base or "https://store.steampowered.com"

    results: dict[str, tuple[bool, str, str]] = {}
    accounts_to_run: list[tuple[str, str, SteamNextAccount]] = []

    for sid in steamids:
        steam_name = await get_steam_nickname(sid)
        acc = await SteamNextAccount.get_account(sid)
        if not acc or not acc.access_token or not acc.session_id:
            results[sid] = (False, steam_name, "仅绑定未登录")
        else:
            accounts_to_run.append((steam_name, sid, acc))

    for acc_idx, (steam_name, sid, acc) in enumerate(accounts_to_run):
        session = _build_store_session(acc)
        account_failed = False
        fail_reason = ""

        for r in range(rounds_per_account):
            logger.info(
                f"[SteamDiscoveryQueue] 开始执行账号 {steam_name}({sid}) "
                f"第 {r + 1}/{rounds_per_account} 轮探索队列..."
            )
            try:
                queue = await asyncio.to_thread(
                    _fetch_queue_sync, session, store_base_url, acc.session_id
                )
                if queue:
                    for appid in queue:
                        await asyncio.to_thread(
                            _clear_app_sync, session, store_base_url, acc.session_id, appid
                        )
                        await asyncio.sleep(0.3)
                logger.info(
                    f"[SteamDiscoveryQueue] 账号 {steam_name}({sid}) "
                    f"第 {r + 1} 轮探索完成（已清空 {len(queue)} 个游戏）"
                )
            except SteamAuthExpiredError as e:
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

    results = await execute_queue_for_steamids(bound_steamids)

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

    try:
        push_group = SteamConfig.get_config("QueuePushGroup").data
    except Exception:
        push_group = True

    try:
        push_private = SteamConfig.get_config("QueuePushPrivate").data
    except Exception:
        push_private = False

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
    results = await execute_queue_for_steamids(all_steamids_ordered)

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
                logger.warning(
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
                logger.warning(
                    f"[SteamDiscoveryQueue] 向用户 {sub.user_id} 私聊推送探索结果失败: {e}"
                )
