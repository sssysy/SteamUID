from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse, Response

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.web_app import app

from ..SteamConfig import SteamConfig
from .asf_client import ASFClient

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_TEXTURE2D_DIR = Path(__file__).parent / "texture2d"
_ICON_PATH = Path(__file__).parents[1] / "ICON.png"

LOGIN_TTL_S = 300
LOGIN_POLL_INTERVAL = 1.5


@dataclass
class LoginState:
    """ASF 登录会话状态"""

    user_id: str
    bot_id: str
    group_id: str | None
    created_at: float
    status: str = "pending"  # "pending" | "need_2fa" | "success" | "failed"
    bot_name: str = ""
    input_type: str = "TwoFactorAuthentication"
    steamid64: str = ""
    msg: str = ""


LOGIN_CACHE: dict[str, LoginState] = {}


def _auth_token(user_id: str) -> str:
    """生成用户认证 token"""
    return hashlib.sha256(f"asf_{user_id}_{time.time()}".encode()).hexdigest()[:8]


def _login_base_url() -> str:
    """获取 gscore 回调与网页访问基础 URL"""
    base = SteamConfig.get_config("gscoreBaseURL").data.strip()
    return base.rstrip("/") if base else "http://127.0.0.1:8765"


def _sanitize_bot_name(user_id: str) -> str:
    """生成 ASF Bot 名称（确保符合 ASF 命名规范）"""
    safe_id = "".join(c for c in str(user_id) if c.isalnum() or c == "_")
    return f"SteamUID_{safe_id}"


class _LoginPayload(BaseModel):
    auth: str
    username: str
    password: str


class _TwoFactorPayload(BaseModel):
    auth: str
    code: str


# =========================================================
# Web 路由与静态资源服务
# =========================================================

@app.get("/steam/asf/style.css")
@app.get("/steam/asf/static/style.css")
async def asf_static_css():
    """提供 style.css"""
    css_path = _TEMPLATES_DIR / "style.css"
    if css_path.exists():
        return Response(content=css_path.read_text(encoding="utf-8"), media_type="text/css")
    return Response(status_code=404)


@app.get("/steam/asf/texture2d/{filename}")
@app.get("/steam/texture2d/{filename}")
@app.get("/steam/asf/static/{filename}")
async def asf_static_file(filename: str):
    """提供静态图片资源"""
    if filename == "ICON.png" and _ICON_PATH.exists():
        return Response(content=_ICON_PATH.read_bytes(), media_type="image/png")
    
    file_path = _TEXTURE2D_DIR / filename
    if file_path.exists():
        media_type = "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else "image/png"
        return Response(content=file_path.read_bytes(), media_type=media_type)
    
    return Response(status_code=404)


@app.get("/steam/asf/login")
@app.get("/steam/asf/{auth_token}")
async def asf_login_entry(request: Request, auth_token: str | None = None):
    """ASF 网页登录主入口"""
    token = auth_token or request.query_params.get("state", "") or request.query_params.get("auth", "")
    state = LOGIN_CACHE.get(token)

    if not token or not state:
        return HTMLResponse("<h3>登录会话不存在或已过期，请重新在群内触发命令</h3>", status_code=400)
    if time.time() - state.created_at > LOGIN_TTL_S:
        LOGIN_CACHE.pop(token, None)
        return HTMLResponse("<h3>登录会话已过期，请重新在群内触发命令</h3>", status_code=400)

    index_html = _TEMPLATES_DIR / "index.html"
    if not index_html.exists():
        return HTMLResponse("<h3>登录页面模板丢失</h3>", status_code=500)

    html_content = index_html.read_text(encoding="utf-8")
    # 注入 auth token 到隐藏域中
    html_content = html_content.replace('value="{{ auth | default(\'\') }}"', f'value="{token}"')
    return HTMLResponse(html_content, status_code=200)


@app.get("/steam/asf/success")
async def asf_login_success():
    """ASF 登录成功反馈页"""
    success_html = _TEMPLATES_DIR / "success.html"
    if not success_html.exists():
        return HTMLResponse("<h3>登录绑定成功</h3>", status_code=200)
    return HTMLResponse(success_html.read_text(encoding="utf-8"), status_code=200)


# =========================================================
# 前端 AJAX API 接口
# =========================================================

@app.post("/steam/asf/api/login")
async def asf_api_login(payload: _LoginPayload):
    """处理账号密码提交并对接 ASF"""
    token = payload.auth
    state = LOGIN_CACHE.get(token)

    if not state or time.time() - state.created_at > LOGIN_TTL_S:
        return JSONResponse({"ok": False, "msg": "登录会话已过期，请重新在群内获取链接"})

    bot_name = _sanitize_bot_name(state.user_id)
    state.bot_name = bot_name

    # 向 ASF 创建或更新并启动 Bot
    created = await ASFClient.create_or_update_bot(bot_name, payload.username, payload.password)
    if not created:
        return JSONResponse({"ok": False, "msg": "连接 ASF IPC 服务失败，请联系管理员检查配置"})

    # 轮询鉴权状态（最长等待 5 秒）
    poll_res = await ASFClient.poll_bot_status(bot_name, max_wait_seconds=5.0)
    status = poll_res.get("status")

    if status == "logged_in":
        steamid64 = poll_res.get("steamid64", "")
        state.status = "success"
        state.steamid64 = steamid64
        LOGIN_CACHE[token] = state
        return JSONResponse({
            "ok": True,
            "done": True,
            "steamid64": steamid64,
            "redirect": "/steam/asf/success",
        })
    elif status == "need_2fa":
        state.status = "need_2fa"
        state.input_type = poll_res.get("input_type", "TwoFactorAuthentication")
        LOGIN_CACHE[token] = state
        return JSONResponse({
            "ok": True,
            "need_2fa": True,
            "hint": poll_res.get("hint", "请输入您的 Steam 手机令牌或邮箱验证码"),
        })
    else:
        # 若仍在 pending，通常为需要 2FA 提示
        state.status = "need_2fa"
        LOGIN_CACHE[token] = state
        return JSONResponse({
            "ok": True,
            "need_2fa": True,
            "hint": "请输入您的 Steam 手机令牌或邮箱验证码",
        })


@app.post("/steam/asf/api/2fa")
async def asf_api_2fa(payload: _TwoFactorPayload):
    """处理两步验证码提交并对接 ASF"""
    token = payload.auth
    state = LOGIN_CACHE.get(token)

    if not state or time.time() - state.created_at > LOGIN_TTL_S:
        return JSONResponse({"ok": False, "msg": "登录会话已过期，请重新获取链接"})

    bot_name = state.bot_name or _sanitize_bot_name(state.user_id)
    code = payload.code.strip().upper()

    # 向 ASF 提交 2FA 凭据
    input_ok = await ASFClient.input_credential(bot_name, state.input_type, code)
    if not input_ok:
        return JSONResponse({"ok": False, "msg": "向 ASF 提交两步验证凭据失败"})

    # 等待登录成功（最多等待 8 秒）
    poll_res = await ASFClient.poll_bot_status(bot_name, max_wait_seconds=8.0)
    if poll_res.get("status") == "logged_in":
        steamid64 = poll_res.get("steamid64", "")
        state.status = "success"
        state.steamid64 = steamid64
        LOGIN_CACHE[token] = state
        return JSONResponse({
            "ok": True,
            "done": True,
            "steamid64": steamid64,
            "redirect": "/steam/asf/success",
        })

    return JSONResponse({"ok": False, "msg": "两步验证码错误或已失效，请重新输入"})


# =========================================================
# Bot 命令异步等待登录完成
# =========================================================

async def _wait(auth_token: str) -> LoginState | None:
    """轮询等待用户完成网页端登录"""
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


async def request_asf_login(bot: Bot, ev: Event) -> str | None:
    """触发 ASF 网页登录并等待完成"""
    asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
    if not asf_url:
        await bot.send("未配置 ASF IPC 地址 (steamasfbaseurl)，请管理员在 SteamConfig 中进行配置！")
        return None

    auth_token = _auth_token(ev.user_id)

    # 检查是否已有同用户的进行中会话
    for k, v in list(LOGIN_CACHE.items()):
        if v.user_id == ev.user_id and v.status in ("pending", "need_2fa") and time.time() - v.created_at <= LOGIN_TTL_S:
            await bot.send("您已有进行中的 ASF 登录会话，请先完成或等待其超时！")
            return None

    base = _login_base_url()
    login_url = f"{base}/steam/asf/login?state={auth_token}"

    await bot.send(f"Steam ASF 登录链接（{int(LOGIN_TTL_S)}秒内有效）：\n{login_url}")

    LOGIN_CACHE[auth_token] = LoginState(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        group_id=ev.group_id,
        created_at=time.time(),
    )

    result = await _wait(auth_token)
    if result is None:
        await bot.send("Steam ASF 登录超时")
        return None
    if result.status != "success":
        await bot.send(f"Steam ASF 登录失败：{result.msg or '未知错误'}")
        return None

    return result.steamid64
