from __future__ import annotations

import asyncio
import re
from typing import Any

from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..SteamASFFarm.farm_service import get_user_asf_target
from ..SteamASFLogin.asf_client import ASFClient
from ..SteamConfig import SteamConfig
from ..utils.api import get_game_info
from ..utils.exceptions import SteamError
from ..utils.utils import maybe_hide_steamid


def _extract_appids(raw_text: str, exclude_ids: set[str] | None = None) -> list[str]:
    """
    从 ASF / ASFEnhance 返回的输出文本中提取所有有效的 Steam AppID
    """
    if not raw_text:
        return []

    if exclude_ids is None:
        exclude_ids = set()

    # 匹配独立的 4~8 位数字
    candidates = re.findall(r"\b\d{4,8}\b", raw_text)
    appids: list[str] = []
    seen: set[str] = set(exclude_ids)

    for cid in candidates:
        # 排除已见过的、或在排除集合中的 ID
        if cid not in seen:
            seen.add(cid)
            appids.append(cid)

    return appids


async def _fetch_game_summary(appid: str) -> dict[str, Any]:
    """获取单款游戏的精简摘要信息"""
    summary = {
        "appid": appid,
        "name": f"AppID {appid}",
        "price": "",
        "discount": 0,
        "genres": [],
        "store_url": f"https://store.steampowered.com/app/{appid}/",
    }
    try:
        info = await get_game_info(appid)
        if isinstance(info, dict) and info.get("success"):
            data = info.get("data", {})
            name = data.get("name")
            if name:
                summary["name"] = name

            is_free = data.get("is_free", False)
            if is_free:
                summary["price"] = "免费"
            else:
                price_overview = data.get("price_overview", {})
                if price_overview:
                    final_formatted = price_overview.get("final_formatted") or ""
                    discount = price_overview.get("discount_percent") or 0
                    summary["discount"] = discount
                    if discount > 0:
                        initial_formatted = price_overview.get("initial_formatted") or ""
                        summary["price"] = f"{final_formatted} (-{discount}%, 原价 {initial_formatted})"
                    else:
                        summary["price"] = final_formatted

            genres = [
                g.get("description")
                for g in data.get("genres", [])
                if isinstance(g, dict) and g.get("description")
            ]
            summary["genres"] = genres[:3]
    except Exception as e:
        logger.debug(f"[SteamASFDiscoveryQueue] 获取 AppID {appid} 详情失败: {e}")

    return summary


async def run_discovery_queue(ev: Event, text: str = "") -> str:
    """
    执行 ASF 队列探索，并返回格式化后的探索结果与游戏列表
    """
    asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
    if not asf_url:
        raise SteamError("未配置 ASF IPC 地址 (steamasfbaseurl)，请管理员在 SteamConfig 中进行配置！")

    bot_name, steamid64, is_asf_bound = await get_user_asf_target(ev, text)
    bot_info = await ASFClient.get_bot(bot_name)

    if not bot_info:
        if not is_asf_bound:
            raise SteamError("您尚未通过 ASF 绑定 Steam 账号，请先使用【asf登录】绑定账号！")
        else:
            raise SteamError("未在 ASF 中找到您的账号实例，请先使用【asf登录】重新登录！")

    # 检查连接状态，若未连接尝试启动
    is_connected = bot_info.get("IsConnectedAndLoggedOn", False)
    if not is_connected:
        await ASFClient.start_bot(bot_name)
        await asyncio.sleep(1.5)
        bot_info = await ASFClient.get_bot(bot_name)
        if not bot_info or not bot_info.get("IsConnectedAndLoggedOn", False):
            raise SteamError(f"ASF 账号 ({bot_name}) 当前未连接到 Steam 网络，请确认账号状态正常后再试。")

    # 准备执行 ASFEnhance 探索指令
    # 尝试指令顺序：ex <bot_name> -> explorer <bot_name> -> ASFE.EXPLORER <bot_name>
    commands_to_try = [
        f"ex {bot_name}",
        f"explorer {bot_name}",
        f"ASFE.EXPLORER {bot_name}",
    ]

    ok = False
    raw_res = ""
    for cmd in commands_to_try:
        ok, raw_res = await ASFClient.send_command(cmd, timeout=45.0)
        # 如果不是未知指令错误，说明该指令已被 ASF/ASFE 接收处理
        if ok and "unknown command" not in raw_res.lower() and "未知命令" not in raw_res:
            break

    if not ok:
        raise SteamError(f"向 ASF 发送探索队列指令失败：{raw_res}")

    if "unknown command" in raw_res.lower() or "未知命令" in raw_res:
        raise SteamError(
            "ASF 未识别探索队列指令！请确认 ASF 服务端已安装【ASFEnhance】插件并已启用。"
        )

    # 排除自身的 SteamID，避免误识别为游戏 AppID
    exclude_ids = set()
    if steamid64:
        exclude_ids.add(str(steamid64))
    s_sid = str(bot_info.get("s_SteamID") or bot_info.get("SteamID") or "")
    if s_sid and s_sid != "0":
        exclude_ids.add(s_sid)

    appids = _extract_appids(raw_res, exclude_ids)

    account_disp = maybe_hide_steamid(steamid64) if steamid64 else bot_name

    # 如果解析出了游戏 AppID，则并发查询游戏信息并生成清单
    if appids:
        tasks = [_fetch_game_summary(aid) for aid in appids]
        games = await asyncio.gather(*tasks)

        lines = [
            "【Steam 探索队列】",
            f"账号：{account_disp}",
            f"状态：探索完成 ✨",
            f"本次探索游戏（共 {len(games)} 款）：",
            "",
        ]

        for i, g in enumerate(games, 1):
            name = g["name"]
            appid = g["appid"]
            price = g["price"]
            genres_str = f" [{'/'.join(g['genres'])}]" if g["genres"] else ""
            store_url = g["store_url"]

            item_lines = [f"{i}. 《{name}》{genres_str}"]
            sub_info = []
            if price:
                sub_info.append(f"价格: {price}")
            sub_info.append(f"AppID: {appid}")
            item_lines.append(f"   {' | '.join(sub_info)}")
            item_lines.append(f"   {store_url}")
            lines.append("\n".join(item_lines))

        lines.append("")
        lines.append("💡 提示：队列探索已完成，可获得对应特卖活动卡牌/贴纸或日常点数奖励！")
        return "\n".join(lines)

    # 如果未直接解析出 AppID（例如返回纯文本汇总信息或今日已全部探索完毕）
    clean_res = raw_res.strip()
    # 清理 ASF 默认前缀格式如 `<BotName> ...`
    clean_res = re.sub(rf"^<.*?>\s*", "", clean_res)

    lines = [
        "【Steam 探索队列】",
        f"账号：{account_disp}",
        f"结果：{clean_res}",
    ]
    return "\n".join(lines)
