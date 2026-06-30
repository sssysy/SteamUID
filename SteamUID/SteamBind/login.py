from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from fastapi import Request
from starlette.responses import PlainTextResponse, RedirectResponse

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.web_app import app

from ..SteamConfig import SteamConfig

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
LOGIN_REDIRECT_URL = "https://github.com/sssysy/steamUID"
LOGIN_TTL_S = 300
LOGIN_POLL_INTERVAL = 2.0

@dataclass
class LoginState:
    """单次 OpenID 登录会话状态。auth_token 作为 LOGIN_CACHE 的 key。"""

    user_id: str
    bot_id: str
    group_id: str | None
    created_at: float
    status: str = "pending"
    steamid64: str = ""
    msg: str = ""

LOGIN_CACHE: dict[str, LoginState] = {}

def _auth_token(user_id: str) -> str:
    """取用户token"""
    return hashlib.sha256(user_id.encode()).hexdigest()[:8]


def _login_base_url() -> str:
    """回调URL"""
    base = SteamConfig.get_config("gscoreBaseURL").data.strip()
    return base or "http://127.0.0.1:8765"


def build_login_url(return_to: str, realm: str) -> str:
    """拼接登录URL"""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID_URL}?{urlencode(params)}"


def _extract_steamid(params: dict) -> str:
    """回调解析steamid64"""
    for key in ("openid.claimed_id", "openid.identity"):
        val = params.get(key, "")
        if val:
            steamid = val.rstrip("/").rsplit("/", 1)[-1]
            if steamid.isdigit():
                return steamid
    return ""


async def _verify_steam_signature(params: dict) -> bool:
    """参数回传steam校验"""
    body: dict[str, str] = {k: v for k, v in params.items() if k.startswith("openid.")}
    if not body.get("openid.sig") or not body.get("openid.signed"):
        return False
    body["openid.mode"] = "check_authentication"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(STEAM_OPENID_URL, data=body)
        return "is_valid:true" in resp.text
    except Exception as error:
        logger.warning(f"[Steam登录] 签名验证请求失败: {error!r}")
        return False


@app.get("/steam/openid")
async def steam_openid_entry(request: Request):
    """发送的链接，重定向到steam"""
    auth_token = request.query_params.get("state", "")
    state = LOGIN_CACHE.get(auth_token)
    if not auth_token or not state or state.status != "pending":
        return PlainTextResponse("登录会话已失效或已使用", status_code=400)
    if time.time() - state.created_at > LOGIN_TTL_S:
        LOGIN_CACHE.pop(auth_token, None)
        return PlainTextResponse("登录会话已过期", status_code=400)

    base = _login_base_url()
    return_to = f"{base}/steam/login/callback?state={auth_token}"
    login_url = build_login_url(return_to, base)
    return RedirectResponse(login_url, status_code=302)


@app.get("/steam/login/callback")
async def steam_openid_callback(request: Request):
    """回调地址"""
    params = dict(request.query_params)
    auth_token = params.get("state", "")

    state = LOGIN_CACHE.get(auth_token)
    if not auth_token or not state or state.status != "pending":
        return PlainTextResponse("登录会话已失效或已使用", status_code=400)
    if time.time() - state.created_at > LOGIN_TTL_S:
        LOGIN_CACHE.pop(auth_token, None)
        return PlainTextResponse("登录会话已过期", status_code=400)

    if not await _verify_steam_signature(params):
        state.status = "failed"
        state.msg = "签名验证失败"
        LOGIN_CACHE[auth_token] = state
        return PlainTextResponse("Steam 登录验证失败", status_code=400)

    steamid64 = _extract_steamid(params)
    if not steamid64:
        state.status = "failed"
        state.msg = "无法解析 steamid"
        LOGIN_CACHE[auth_token] = state
        return PlainTextResponse("无法解析 steamid", status_code=400)

    state.status = "success"
    state.steamid64 = steamid64
    LOGIN_CACHE[auth_token] = state
    return RedirectResponse(LOGIN_REDIRECT_URL, status_code=303)


async def _wait(auth_token: str) -> LoginState | None:
    """轮询登录状态"""
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


async def request_openid_login(bot: Bot, ev: Event) -> str | None:
    """登录流程"""
    auth_token = _auth_token(ev.user_id)

    # 判断已有登录进程
    existing = LOGIN_CACHE.get(auth_token)
    if existing and existing.status == "pending" and time.time() - existing.created_at <= LOGIN_TTL_S:
        await bot.send("已有进行中的 Steam 登录，请先完成或等待其超时")
        return None

    base = _login_base_url()
    short_url = f"{base}/steam/openid?state={auth_token}"

    await bot.send(f"Steam 登录链接（{int(LOGIN_TTL_S)}秒内有效）：\n{short_url}")

    LOGIN_CACHE[auth_token] = LoginState(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        group_id=ev.group_id,
        created_at=time.time(),
    )

    result = await _wait(auth_token)
    if result is None:
        await bot.send("Steam 登录超时")
        return None
    if result.status != "success":
        await bot.send(f"Steam 登录失败：{result.msg}")
        return None
    return result.steamid64
