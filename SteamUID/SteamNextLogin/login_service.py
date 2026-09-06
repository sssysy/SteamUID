# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .web_auth import SteamWebAuth
from ..SteamBind.bind_service import do_bind
from ..SteamConfig import SteamConfig
from ..utils.database.models import SteamNextAccount
from ..utils.exceptions import SteamValidationError

LOGIN_TTL_S = 300.0  # 5分钟会话有效期
LOGIN_POLL_INTERVAL = 2.0


@dataclass
class LoginSessionState:
    """单次 Web 登录会话状态"""
    user_id: str
    bot_id: str
    group_id: Optional[str]
    user_type: str
    WS_BOT_ID: Optional[str]
    bot_self_id: Optional[str]
    created_at: float
    status: str = "pending"  # pending, need_2fa, success, failed
    steamid64: str = ""
    msg: str = ""
    auth_instance: Optional[SteamWebAuth] = None


LOGIN_CACHE: dict[str, LoginSessionState] = {}


def generate_auth_token(user_id: str) -> str:
    """生成唯一短 token 作为状态索引"""
    raw = f"{user_id}_{time.time()}_{hashlib.md5(user_id.encode()).hexdigest()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def get_base_url() -> str:
    """获取外网/穿透访问基地址"""
    base = SteamConfig.get_config("gscoreBaseURL").data.strip()
    return base or "http://127.0.0.1:8765"


async def save_account_credentials(creds: dict):
    """持久化保存凭据到 SteamNextAccount 表"""
    steamid64 = creds.get("steamid64")
    if not steamid64:
        return

    await SteamNextAccount.upsert_account(
        steamid64=steamid64,
        account_name=creds.get("account_name"),
        access_token=creds.get("access_token"),
        refresh_token=creds.get("refresh_token"),
        session_id=creds.get("session_id"),
        cookies_json=json.dumps(creds.get("cookies", {}), ensure_ascii=False),
        updated_at=int(time.time()),
    )
    logger.info(f"[SteamNextLogin] 账号 {steamid64} 授权凭据已成功写入数据库")


async def complete_login_binding(state: LoginSessionState, ev: Event) -> tuple[str, str]:
    """
    完成登录后联动现有 SteamBind
    若用户已经绑定了该 steamid，直接视为凭据更新，不报错阻断。
    """
    steamid64 = state.steamid64
    try:
        success_msg, warning = await do_bind(ev, steamid64)
        return success_msg, warning
    except SteamValidationError as e:
        err_str = str(e)
        if "你已在该群绑定该steamid" in err_str or "已绑定" in err_str:
            return "Steam 账号凭据更新成功！", ""
        logger.warning(f"[SteamNextLogin] 联动绑定提示: {err_str}")
        return f"登录成功，绑定提示: {err_str}", ""
    except Exception as e:
        logger.exception(f"[SteamNextLogin] 联动绑定发生异常: {e}")
        return "登录成功，自动联动绑定时遇到问题，请手动尝试绑定。", ""


async def _wait_for_login(auth_token: str) -> Optional[LoginSessionState]:
    """轮询等待用户在网页端操作完成"""
    waited = 0.0
    while waited < LOGIN_TTL_S:
        state = LOGIN_CACHE.get(auth_token)
        if not state:
            return None
        if state.status in ("success", "failed"):
            LOGIN_CACHE.pop(auth_token, None)
            return state
        await asyncio.sleep(LOGIN_POLL_INTERVAL)
        waited += LOGIN_POLL_INTERVAL

    LOGIN_CACHE.pop(auth_token, None)
    return None


async def request_web_login(bot: Bot, ev: Event) -> Optional[str]:
    """
    发起 Web 登录命令流程
    生成登录链接，发送给用户，并等待登录完成
    """
    # 检查是否有未超时的进行中会话
    for k, v in list(LOGIN_CACHE.items()):
        if v.user_id == ev.user_id and v.status in ("pending", "need_2fa"):
            if time.time() - v.created_at <= LOGIN_TTL_S:
                await bot.send("您已有进行中的 Steam 登录会话，请先在浏览器完成或等待其超时！")
                return None

    auth_token = generate_auth_token(ev.user_id)
    base_url = get_base_url()
    login_url = f"{base_url}/steam/login?state={auth_token}"

    state = LoginSessionState(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        group_id=ev.group_id,
        user_type=ev.user_type,
        WS_BOT_ID=ev.WS_BOT_ID,
        bot_self_id=ev.bot_self_id,
        created_at=time.time(),
    )
    LOGIN_CACHE[auth_token] = state

    # 发送登录提示
    await bot.send(
        f"Steam 网页授权登录链接（{int(LOGIN_TTL_S)} 秒内有效）：\n"
        f"{login_url}\n"
        f"请点击或复制链接至浏览器完成登录验证。"
    )

    # 异步等待登录结果
    result = await _wait_for_login(auth_token)
    if result is None:
        await bot.send("Steam 登录已超时，请重新发送命令。")
        return None

    if result.status != "success":
        await bot.send(f"Steam 登录失败：{result.msg or '未知原因'}")
        return None

    # 登录成功，联动绑定
    bind_msg, warn = await complete_login_binding(result, ev)
    full_reply = f"【登录成功】\nSteamID: {result.steamid64}\n{bind_msg}"
    if warn:
        full_reply += f"\n{warn}"

    await bot.send(full_reply)
    return result.steamid64
