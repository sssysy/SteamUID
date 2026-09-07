# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import re
from typing import List, Optional, Tuple

import requests
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.api import get_user_Summaries
from ..utils.database.models import SteamBind, SteamIDInfo, SteamNextAccount
from ..utils.exceptions import SteamValidationError
from ..utils.next.session import get_valid_session
from ..utils.utils import auto2steamid64

# Steam CDKey 格式校验正则：支持 15 位 (5-5-5)、25 位 (5-5-5-5-5) 等标准格式
CDK_PATTERN = re.compile(r"^[A-Z0-9]{4,5}(-[A-Z0-9]{4,5}){2,4}$")

# Steam 错误码映射表
ERROR_CODE_MAP = {
    9: "已拥有该产品",
    13: "缺少本体游戏/前置DLC",
    14: "无效的代码",
    15: "已被其他账户兑换",
    24: "地区限制（锁区）",
    53: "尝试失败过多被限频",
}


def normalize_and_validate_cdk(raw_k: str) -> Optional[str]:
    """
    清洗并校验单枚 CDKey。
    若是 15 或 25 位不带连字符的纯字母数字，自动补充连字符；
    验证通过返回规整后的大写 CDKey，否则返回 None。
    """
    k = raw_k.strip().upper()
    if not k:
        return None

    # 自动补全连字符
    if "-" not in k:
        if len(k) == 15 and k.isalnum():
            k = f"{k[:5]}-{k[5:10]}-{k[10:]}"
        elif len(k) == 25 and k.isalnum():
            k = f"{k[:5]}-{k[5:10]}-{k[10:15]}-{k[15:20]}-{k[20:]}"

    if CDK_PATTERN.match(k):
        return k
    return None


async def get_account_display_name(steamid64: str) -> str:
    """获取账号的展示昵称（依次尝试 SteamIDInfo、SteamNextAccount、get_user_Summaries）"""
    try:
        user_info_raw = await SteamIDInfo.get_steamuserinfo(steamid64)
        if user_info_raw:
            info = json.loads(user_info_raw)
            if isinstance(info, dict) and info.get("personaname"):
                return str(info["personaname"])
    except Exception:
        pass

    try:
        acc = await SteamNextAccount.get_account(steamid64)
        if acc and acc.account_name:
            return str(acc.account_name)
    except Exception:
        pass

    try:
        summaries = await get_user_Summaries(steamid64)
        if summaries and isinstance(summaries, list) and summaries[0].get("personaname"):
            return str(summaries[0]["personaname"])
    except Exception:
        pass

    return "Steam用户"


async def parse_input_arguments(bot_id: str, user_id: str, raw_text: str) -> Tuple[str, List[str]]:
    """
    解析用户输入的参数，返回 (target_steamid, cleaned_cdks)。
    若格式或前置校验失败，抛出 SteamValidationError。
    规则：
      - 命令 参数1 参数2：参数1为指定 steamid/好友代码，参数2为 CDK 列表
      - 命令 参数1：参数1为 CDK 列表，目标账号回退至当前用户绑定的主账号
      - 有任何传错就报错
    """
    if not raw_text or not raw_text.strip():
        raise SteamValidationError(
            "未检测到输入的 CDKey！\n"
            "格式：\n"
            "  steam激活 [steamid/好友代码] <cdk列表>"
        )

    # 规范化：消除逗号两侧空格并将中文逗号统一为半角逗号
    text = re.sub(r"\s*[,，]\s*", ",", raw_text.strip())
    args = text.split()

    if len(args) == 1:
        raw_steamid = None
        raw_cdk_list = args[0]
    elif len(args) == 2:
        raw_steamid = args[0]
        raw_cdk_list = args[1]
    else:
        raise SteamValidationError(
            "指令参数数量错误！正常指令格式为：\n"
            "  steam激活 [steamid/好友代码] <cdk列表>"
        )

    if raw_steamid is not None:
        converted_sid = auto2steamid64(raw_steamid)
        if not converted_sid or len(converted_sid) != 17:
            raise SteamValidationError(f"参数 1 格式错误：{raw_steamid} 不是有效的 SteamID 或好友代码！")
        binds = await SteamBind.get_bind_by_steamid(converted_sid)
        if not binds:
            raise SteamValidationError(f"未找到账号 {converted_sid} 的绑定记录，请先使用【steam绑定】进行绑定！")
        if not any(str(b.bot_id) == str(bot_id) and str(b.user_id) == str(user_id) for b in binds):
            raise SteamValidationError(f"账号 {converted_sid} 未绑定到当前用户，无法执行激活！")
        target_steamid = converted_sid
    else:
        binds = await SteamBind.get_binds_by_user_id(bot_id, user_id)
        if not binds:
            raise SteamValidationError("未找到绑定的 Steam 账号，请先使用【steam绑定 <SteamID/好友代码>】进行绑定！")
        main_bind = next((b for b in binds if b.is_main_id), binds[0])
        target_steamid = main_bind.steamid64

    # 提取并严格校验 CDK 列表
    cdk_tokens = [k.strip() for k in re.split(r"[,，\n]+", raw_cdk_list) if k.strip()]
    if not cdk_tokens:
        raise SteamValidationError("未检测到要激活的 CDKey，请检查输入的 CDKey 列表！")

    cleaned_cdks: List[str] = []
    for idx, raw_k in enumerate(cdk_tokens, start=1):
        valid_cdk = normalize_and_validate_cdk(raw_k)
        if not valid_cdk:
            raise SteamValidationError(
                f"CDKey 格式有误：[{idx}] {raw_k} 不是有效的 Steam 激活码格式！\n"
                "已中止本次操作以保护账号防风控。"
            )
        cleaned_cdks.append(valid_cdk)

    return target_steamid, cleaned_cdks


async def handle_cdkey_activation(bot: Bot, ev: Event):
    """处理 Steam CDKey 激活全流程"""
    raw_text = ev.text.strip()
    target_steamid, cleaned_cdks = await parse_input_arguments(ev.bot_id, ev.user_id, raw_text)

    # 校验是否已完成 WebAuth 授权
    acc = await SteamNextAccount.get_account(target_steamid)
    if not acc or not (acc.access_token or acc.refresh_token):
        await bot.send(
            f"未检测到账号 {target_steamid} 的网页登录授权！\n"
            "请先向机器人发送【steam登录】完成授权后再进行激活。"
        )
        return

    # 获取账号昵称
    account_name = await get_account_display_name(target_steamid)

    # 1. 组装二次确认提示语
    cdk_lines = "\n".join(f"[{i}] {k}" for i, k in enumerate(cleaned_cdks, start=1))
    confirm_msg = (
        f"[Steam CDKey 激活流程]\n"
        f"即将将如下CDKey:\n"
        f"{cdk_lines}\n"
        f"激活到账户【{account_name}】({target_steamid}) 中\n"
        f"请仔细确认所有数据是否正确！\n"
        f"正确请发送【steam确认激活】，否则请回复任意文本！"
    )

    # 2. 多步会话等待用户回复确认（超时 60s）
    resp = await bot.receive_resp(confirm_msg, timeout=60)
    if resp is None:
        await bot.send("操作已超时，已取消本次激活流程。")
        return

    # 严格匹配前缀指令
    if resp.text.strip() != "steam确认激活":
        await bot.send("[Steam CDKey 激活流程] 已取消本次激活任务。")
        return

    await bot.send("[Steam CDKey 激活流程] 开始执行激活任务，请稍候...")

    # 3. 循环请求 Steam 商店接口
    success_list: List[str] = []
    fail_list: List[str] = []

    for i, cdk in enumerate(cleaned_cdks):
        session = await get_valid_session(target_steamid)
        if not session:
            fail_list.append(f"[{len(fail_list) + 1}] {cdk} | 获取登录凭据失败或授权已过期")
            continue

        sessionid = session.cookies.get("sessionid", domain="store.steampowered.com") or session.cookies.get("sessionid")
        url = "https://store.steampowered.com/account/ajaxregisterkey/"
        data = {
            "product_key": cdk,
            "sessionid": sessionid,
        }
        headers = {
            "Referer": "https://store.steampowered.com/account/registerkey/",
            "Origin": "https://store.steampowered.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        try:
            resp_obj = await asyncio.to_thread(session.post, url, data=data, headers=headers, timeout=15)
            if resp_obj.status_code != 200:
                fail_list.append(f"[{len(fail_list) + 1}] {cdk} | HTTP {resp_obj.status_code}")
                continue

            res_json = resp_obj.json()
            result_code = res_json.get("purchase_result_details")

            if result_code == 0:
                # 激活成功：获取入库产品名
                items = res_json.get("purchase_receipt_info", {}).get("line_items", [])
                game_name = "未知游戏"
                if items and isinstance(items, list) and items[0].get("line_item_description"):
                    game_name = items[0]["line_item_description"]
                # 成功显示格式：游戏名称 | xxxxx-xxxxx-xxxxx
                success_list.append(f"[{len(success_list) + 1}] {game_name} | {cdk}")
            elif result_code == 53:
                # 限频熔断保护：立即中止后续所有请求
                fail_list.append(f"[{len(fail_list) + 1}] {cdk} | 尝试失败过多被限频")
                for rem_idx in range(i + 1, len(cleaned_cdks)):
                    rem_k = cleaned_cdks[rem_idx]
                    fail_list.append(f"[{len(fail_list) + 1}] {rem_k} | 已跳过(触发限频熔断)")
                logger.warning(f"[SteamCDKey] 账号 {target_steamid} 触发 53 限频风控，已熔断后续激活")
                break
            else:
                reason = ERROR_CODE_MAP.get(result_code, f"激活失败(代码: {result_code})")
                fail_list.append(f"[{len(fail_list) + 1}] {cdk} | {reason}")

        except requests.exceptions.Timeout:
            fail_list.append(f"[{len(fail_list) + 1}] {cdk} | 请求 Steam 超时")
        except Exception as e:
            logger.warning(f"[SteamCDKey] 激活 ***{cdk[-3:]} 发生异常: {e}")
            fail_list.append(f"[{len(fail_list) + 1}] {cdk} | 网络请求异常")

        # 若后续还有 CDK，等待安全间隔
        if i < len(cleaned_cdks) - 1:
            await asyncio.sleep(1.5)

    # 4. 组装最终任务汇报文本
    report_blocks = [
        "[Steam CDKey 激活流程]\nCDKey激活任务结束",
    ]

    if success_list:
        report_blocks.append(f"成功：{len(success_list)}个\n" + "\n".join(success_list))

    if fail_list:
        report_blocks.append(f"失败：{len(fail_list)}个\n" + "\n".join(fail_list))

    if not success_list and not fail_list:
        report_blocks.append("未执行任何激活操作。")

    final_report = "\n\n".join(report_blocks)
    await bot.send(final_report)
