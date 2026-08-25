from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
import json
from typing import Any

from gsuid_core.logger import logger

from ..SteamASFLogin.asf_client import ASFClient
from ..SteamASFLogin.login import _sanitize_bot_name
from ..SteamConfig import SteamConfig
from ..utils.api import get_user_Summaries
from ..utils.database.models import SteamBind, SteamIDInfo
from ..utils.utils import maybe_hide_steamid, get_enabled_push_events


async def get_steam_nickname(steamid64: str, fallback: str = "未知用户") -> str:
    """获取 Steam 用户昵称（优先从数据库缓存中获取，缺失则调用 API）"""
    if not steamid64:
        return fallback
    try:
        info_json = await SteamIDInfo.get_steamuserinfo(steamid64)
        if info_json:
            info = json.loads(info_json)
            name = info.get("personaname")
            if name:
                return name
        summaries = await get_user_Summaries(steamid64)
        if summaries:
            await SteamIDInfo.upsert_steamuserinfo(
                steamid64, json.dumps(summaries[0], ensure_ascii=False)
            )
            return summaries[0].get("personaname") or fallback
    except Exception as e:
        logger.debug(f"[SteamASFDiscoveryQueue] 获取用户昵称失败 sid={steamid64}: {e!r}")
    return maybe_hide_steamid(steamid64) if steamid64 else fallback


async def run_auto_discovery_queue_job() -> None:
    """自动探索队列定时任务：探索所有开启自动探索队列的 Steam 账号，并在结束后按群发送汇总通知"""
    asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
    if not asf_url:
        logger.warning("[SteamASFDiscoveryQueue] 未配置 ASF IPC 地址 (steamasfbaseurl)，跳过自动探索任务")
        return

    binds = await SteamBind.get_all_auto_discovery_queue_binds()
    if not binds:
        logger.info("[SteamASFDiscoveryQueue] 当前无开启自动探索队列的绑定账号")
        return

    # 按用户/Bot 实例去重执行，避免同一个账号在多个群重复触发探索命令
    # bot_name -> {"user_id": ..., "steamid64": ..., "binds": [...]}
    bot_targets: dict[str, dict[str, Any]] = {}
    for bind in binds:
        bot_name = _sanitize_bot_name(bind.user_id)
        if bot_name not in bot_targets:
            bot_targets[bot_name] = {
                "user_id": bind.user_id,
                "steamid64": bind.steamid64,
                "binds": [],
            }
        bot_targets[bot_name]["binds"].append(bind)

    logger.info(f"[SteamASFDiscoveryQueue] 开始执行自动探索队列任务，待探索 Bot 数量: {len(bot_targets)}")

    # 存储每个 bot_name 的执行结果: (is_success: bool, nickname: str, error_reason: str)
    bot_results: dict[str, tuple[bool, str, str]] = {}

    for bot_name, target_info in bot_targets.items():
        sid = target_info["steamid64"]
        nickname = await get_steam_nickname(sid, fallback=target_info["user_id"])

        try:
            bot_info = await ASFClient.get_bot(bot_name)
            if not bot_info:
                bot_results[bot_name] = (False, nickname, "未在ASF中找到账号实例")
                continue

            is_connected = bot_info.get("IsConnectedAndLoggedOn", False)
            if not is_connected:
                bot_results[bot_name] = (False, nickname, "ASF账号未登录或离线")
                continue

            ok, raw_res = await ASFClient.send_command(f"ex {bot_name}", timeout=60.0)
            if ok:
                bot_results[bot_name] = (True, nickname, "")
            else:
                bot_results[bot_name] = (False, nickname, f"探索失败: {raw_res}")
        except Exception as e:
            logger.error(f"[SteamASFDiscoveryQueue] 探索 Bot {bot_name} 发生异常: {e!r}")
            bot_results[bot_name] = (False, nickname, f"执行异常: {e}")

        # 稍微间隔，避免请求过于密集
        await asyncio.sleep(1.0)

    # 检查推送总开关中是否开启【自动探索完毕】
    enabled_push_events = get_enabled_push_events()
    if "自动探索完毕" not in enabled_push_events:
        logger.info("[SteamASFDiscoveryQueue] 推送总开关未开启【自动探索完毕】，静默执行完毕，不发送通知。")
        return

    # 按群聊/私聊维度组织发送结果
    # group_key -> list[SteamBind]
    group_map: dict[tuple[str, str | None, str], list[SteamBind]] = defaultdict(list)
    for bind in binds:
        group_key = (bind.bot_id, bind.group_id, bind.user_type)
        group_map[group_key].append(bind)

    current_date = datetime.now().strftime("%Y-%m-%d")

    for group_key, group_binds in group_map.items():
        if not group_binds:
            continue

        # 统计该群/会话下的成功与失败情况（按 steamid64 去重）
        seen_sids: set[str] = set()
        success_count = 0
        failure_items: list[tuple[str, str]] = []  # (nickname, fail_reason)

        for bind in group_binds:
            sid = bind.steamid64
            if sid in seen_sids:
                continue
            seen_sids.add(sid)

            bot_name = _sanitize_bot_name(bind.user_id)
            res = bot_results.get(bot_name)
            if not res:
                continue

            is_success, nickname, fail_reason = res
            if is_success:
                success_count += 1
            else:
                failure_items.append((nickname, fail_reason))

        # 格式化消息：
        # [自动探索队列任务]
        # 时间：xxxx-xx-xx
        # 成功：x个
        # 失败：
        # steam昵称（失败原因）
        lines = [
            "[自动探索队列任务]",
            f"时间：{current_date}",
            f"成功：{success_count}个",
        ]
        if failure_items:
            lines.append("失败：")
            for nick, reason in failure_items:
                lines.append(f"{nick}（{reason}）")
        else:
            lines.append("失败：0个")

        message_text = "\n".join(lines)

        try:
            # 选用该群的第一个 bind 发送
            await group_binds[0].send(message_text)
            logger.info(f"[SteamASFDiscoveryQueue] 已向会话 {group_key} 推送自动探索结果")
        except Exception as e:
            logger.warning(f"[SteamASFDiscoveryQueue] 向 {group_key} 发送探索结果失败: {e!r}")
