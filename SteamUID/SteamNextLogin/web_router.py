# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Optional

from fastapi import Request
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse, Response

from gsuid_core.logger import logger
from gsuid_core.web_app import app

from .login_service import LOGIN_CACHE, LOGIN_TTL_S, save_account_credentials
from .web_auth import (
    AuthCodeInvalid,
    LoginIncorrect,
    SteamAuthError,
    SteamWebAuth,
    TwoFactorAuthRequired,
)

_CUR_DIR = Path(__file__).parent
_TEMPLATES_DIR = _CUR_DIR / "templates"
_TEXTURE2D_DIR = _CUR_DIR / "texture2d"
_ICON_PATH = _CUR_DIR.parent.parent / "ICON.png"


def _get_icon_base64() -> str:
    """读取根目录 ICON.png 并编码为 Base64"""
    if _ICON_PATH.exists():
        data = base64.b64encode(_ICON_PATH.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{data}"
    return "/steam/login/logo"


class _LoginPayload(BaseModel):
    auth: str
    username: str
    password: str


class _TwoFactorPayload(BaseModel):
    auth: str
    code: str


class _AppConfirmPayload(BaseModel):
    auth: str


@app.get("/steam/login/logo")
async def steam_login_logo():
    """提供插件 Logo 图片"""
    if _ICON_PATH.exists():
        return Response(content=_ICON_PATH.read_bytes(), media_type="image/png")
    return Response(status_code=404)


@app.get("/steam/login/style.css")
async def steam_login_style():
    """提供页面 CSS 样式文件"""
    css_path = _TEMPLATES_DIR / "style.css"
    if css_path.exists():
        return Response(content=css_path.read_bytes(), media_type="text/css")
    return Response(status_code=404)


@app.get("/steam/login/texture2d/{filename}")
async def steam_login_static_file(filename: str):
    """提供背景图片等静态资源"""
    file_path = _TEXTURE2D_DIR / filename
    if file_path.exists():
        media_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
        return Response(content=file_path.read_bytes(), media_type=media_type)
    return Response(status_code=404)


@app.get("/steam/login/success")
async def steam_login_success():
    """登录成功反馈页"""
    success_html = _TEMPLATES_DIR / "success.html"
    if not success_html.exists():
        return HTMLResponse("<h3>登录绑定成功，现可安全关闭本窗口</h3>", status_code=200)
    return HTMLResponse(success_html.read_text(encoding="utf-8"), status_code=200)


@app.get("/steam/login")
async def steam_login_entry(request: Request):
    """网页登录入口页，接收 ?state=xxx 或 ?auth=xxx"""
    token = (request.query_params.get("state") or request.query_params.get("auth") or "").strip()
    state = LOGIN_CACHE.get(token)

    if not token or not state:
        return HTMLResponse(
            "<h3>登录会话不存在或已过期，请重新在聊天界面发送命令获取链接。</h3>",
            status_code=400,
        )

    if time.time() - state.created_at > LOGIN_TTL_S:
        LOGIN_CACHE.pop(token, None)
        return HTMLResponse(
            "<h3>登录会话已超时失效，请重新发送命令。</h3>",
            status_code=400,
        )

    index_html = _TEMPLATES_DIR / "index.html"
    if not index_html.exists():
        return HTMLResponse("<h3>登录模板丢失，请检查后台文件完整性。</h3>", status_code=500)

    html_content = index_html.read_text(encoding="utf-8")
    # 注入 auth token
    html_content = html_content.replace("value=\"{{ auth | default('') }}\"", f'value="{token}"')
    # 注入 Logo
    html_content = html_content.replace("{{ logo_src }}", _get_icon_base64())
    # 注入登录校验码
    html_content = html_content.replace("{{ verify_code }}", str(state.user_id or ""))

    return HTMLResponse(html_content, status_code=200)


@app.post("/steam/login/api/login")
async def steam_api_login(payload: _LoginPayload):
    """处理用户账号密码提交"""
    token = payload.auth
    state = LOGIN_CACHE.get(token)

    if not state or time.time() - state.created_at > LOGIN_TTL_S:
        return JSONResponse({"ok": False, "msg": "登录会话已超时过期，请重新在聊天界面获取链接"})

    username = payload.username.strip()
    password = payload.password.strip()

    if not username or not password:
        return JSONResponse({"ok": False, "msg": "请输入账号名称和密码"})

    try:
        auth_instance = SteamWebAuth(username=username, password=password)
        state.auth_instance = auth_instance

        # 执行初次登录
        res = await auth_instance.start_session()

        if res.get("done"):
            # 无需 2FA，直接完成
            creds = auth_instance.get_credentials()
            await save_account_credentials(creds)

            state.status = "success"
            state.steamid64 = res["steamid64"]
            LOGIN_CACHE[token] = state

            return JSONResponse({
                "ok": True,
                "done": True,
                "steamid64": res["steamid64"],
                "redirect": "/steam/login/success",
            })
        else:
            # 需要 2FA
            state.status = "need_2fa"
            LOGIN_CACHE[token] = state

            return JSONResponse({
                "ok": True,
                "done": False,
                "need_2fa": True,
                "can_app_confirm": res.get("can_app_confirm", False),
                "hint": res.get("hint", "请输入手机令牌 5 位动态验证码"),
            })

    except LoginIncorrect as e:
        return JSONResponse({"ok": False, "msg": str(e)})
    except SteamAuthError as e:
        return JSONResponse({"ok": False, "msg": f"登录失败: {e}"})
    except Exception as e:
        logger.exception(f"[SteamNextLogin] API 登录异常: {e}")
        return JSONResponse({"ok": False, "msg": "登录请求异常，请检查后台日志或稍后重试"})


@app.post("/steam/login/api/2fa")
async def steam_api_2fa(payload: _TwoFactorPayload):
    """处理用户 2FA 动态令牌或邮箱验证码提交"""
    token = payload.auth
    state = LOGIN_CACHE.get(token)

    if not state or time.time() - state.created_at > LOGIN_TTL_S:
        return JSONResponse({"ok": False, "msg": "登录会话已超时过期，请重新获取链接"})

    code = payload.code.strip().upper()
    if not code:
        return JSONResponse({"ok": False, "msg": "请输入 5 位 Steam 动态令牌码"})

    auth_instance = state.auth_instance
    if not auth_instance:
        return JSONResponse({"ok": False, "msg": "未找到待验证的登录会话，请刷新重试"})

    try:
        res = await auth_instance.submit_2fa_code(code)
        if res.get("done"):
            creds = auth_instance.get_credentials()
            await save_account_credentials(creds)

            state.status = "success"
            state.steamid64 = res["steamid64"]
            LOGIN_CACHE[token] = state

            return JSONResponse({
                "ok": True,
                "done": True,
                "steamid64": res["steamid64"],
                "redirect": "/steam/login/success",
            })
        else:
            return JSONResponse({"ok": False, "msg": "两步验证失败，请重新输入"})

    except AuthCodeInvalid as e:
        return JSONResponse({"ok": False, "msg": str(e)})
    except Exception as e:
        logger.exception(f"[SteamNextLogin] 提交 2FA 异常: {e}")
        return JSONResponse({"ok": False, "msg": "验证码校验异常，请稍后重试"})


@app.post("/steam/login/api/check_confirm")
async def steam_api_check_confirm(payload: _AppConfirmPayload):
    """检查手机 Steam App 确认状态"""
    token = payload.auth
    state = LOGIN_CACHE.get(token)

    if not state or time.time() - state.created_at > LOGIN_TTL_S:
        return JSONResponse({"ok": False, "msg": "登录会话已超时过期"})

    if state.status == "success" and state.steamid64:
        return JSONResponse({
            "ok": True,
            "done": True,
            "steamid64": state.steamid64,
            "redirect": "/steam/login/success",
        })

    auth_instance = state.auth_instance
    if not auth_instance:
        return JSONResponse({"ok": False, "msg": "未找到待验证的登录会话"})

    try:
        res = await auth_instance.check_app_confirmation()
        if res.get("done"):
            creds = auth_instance.get_credentials()
            await save_account_credentials(creds)

            state.status = "success"
            state.steamid64 = res["steamid64"]
            LOGIN_CACHE[token] = state

            return JSONResponse({
                "ok": True,
                "done": True,
                "steamid64": res["steamid64"],
                "redirect": "/steam/login/success",
            })
        else:
            return JSONResponse({
                "ok": False,
                "done": False,
                "msg": res.get("msg", "尚未检测到手机端确认"),
            })
    except Exception as e:
        return JSONResponse({"ok": False, "done": False, "msg": "检测失败"})
