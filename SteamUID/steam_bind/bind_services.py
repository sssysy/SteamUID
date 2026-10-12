"""Steam 绑定 / 解绑 / 查看 的实现与网页回调路由。"""

import time
import asyncio
import secrets
from dataclasses import dataclass
from collections.abc import Sequence

from fastapi import Request
from starlette.responses import Response, RedirectResponse, PlainTextResponse

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.web_app import app

from ..steam_config import SteamConfig
from ..utils.api.openid import build_login_url, verify_callback, extract_steamid64
from ..utils.helper.bind import add_bind, get_binds, remove_bind, session_ids
from ..utils.helper.config import hide_id, base_url
from ..utils.helper.profile import load_profile_assets
from ..utils.helper.steamid import auto2steamid64, steamid64_to_friend_code
from ..utils.render.bind_card import render_bind_card_image
from ..utils.database.model_bind import SteamBind

_OPENID_TTL = 300.0
_POLL_INTERVAL = 2.0
_SUCCESS_URL = "https://github.com/sssysy/SteamUID"


@dataclass
class _LoginSession:
    """单次 OpenID 登录会话，state 作为会话 key。"""

    state: str
    created_at: float
    status: str = "pending"
    steamid64: str = ""
    msg: str = ""


_SESSIONS: dict[str, _LoginSession] = {}


def _expired(session: _LoginSession) -> bool:
    return time.monotonic() - session.created_at > _OPENID_TTL


@app.get("/steam/openid")
async def openid_entry(request: Request) -> Response:
    """用户点开的入口：校验会话后 302 到 Steam 登录页。"""
    state = request.query_params["state"] if "state" in request.query_params else ""
    session = _SESSIONS[state] if state in _SESSIONS else None
    if session is None or session.status != "pending":
        return PlainTextResponse("登录会话已失效或已使用", status_code=400)
    if _expired(session):
        _SESSIONS.pop(state, None)
        return PlainTextResponse("登录会话已过期", status_code=400)

    base = base_url()
    if not base:
        return PlainTextResponse("未配置 GsCore 公网地址", status_code=500)

    return_to = f"{base}/steam/openid/callback?state={state}"
    return RedirectResponse(build_login_url(return_to, base), status_code=302)


@app.get("/steam/openid/callback")
async def openid_callback(request: Request) -> Response:
    """Steam 回调：验签取 steamid64，写回会话供命令侧轮询。"""
    params = {key: value for key, value in request.query_params.items()}
    state = params["state"] if "state" in params else ""
    session = _SESSIONS[state] if state in _SESSIONS else None
    if session is None or session.status != "pending":
        return PlainTextResponse("登录会话已失效或已使用", status_code=400)
    if _expired(session):
        _SESSIONS.pop(state, None)
        return PlainTextResponse("登录会话已过期", status_code=400)

    if not await verify_callback(params):
        session.status = "failed"
        session.msg = "签名验证失败"
        return PlainTextResponse("Steam 登录验证失败", status_code=400)

    steamid64 = extract_steamid64(params)
    if not steamid64:
        session.status = "failed"
        session.msg = "无法解析 steamid"
        return PlainTextResponse("无法解析 steamid", status_code=400)

    session.status = "success"
    session.steamid64 = steamid64
    return RedirectResponse(_SUCCESS_URL, status_code=303)


async def request_openid_login(bot: Bot, ev: Event) -> str:
    """发起网页登录并轮询结果，返回 steamid64；失败抛 ValueError。"""
    base = base_url()
    if not base:
        raise ValueError("未配置 GsCore 公网地址，无法发起 Steam 网页登录")

    state = secrets.token_urlsafe(16)
    session = _LoginSession(state=state, created_at=time.monotonic())
    _SESSIONS[state] = session

    await bot.send(
        f"1. 请携带steam好友码进行绑定！如：steam绑定12345678\n2. 或在 {int(_OPENID_TTL)} 秒内打开链接通过Openid完成 Steam 绑定：\n{base}/steam/openid?state={state}"
    )

    deadline = time.monotonic() + _OPENID_TTL
    try:
        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL)
            if session.status == "success":
                return session.steamid64
            if session.status == "failed":
                raise ValueError(f"Steam 登录失败：{session.msg}")
        raise ValueError("Steam 登录超时，请重新发起")
    finally:
        _SESSIONS.pop(state, None)


async def bind_account(ev: Event, user_id: str, steamid64: str) -> None:
    """校验并写入绑定，新绑定设为当前账户。"""
    profile = await load_profile_assets(steamid64)

    binds = await get_binds(ev, user_id)
    if any(bind.steamid64 == steamid64 for bind in binds):
        raise ValueError(f"该账户已绑定：[{profile.name}]")

    await add_bind(ev, user_id, steamid64, SteamConfig.get_config("DefaultNotifyTypes").data)


async def unbind_account(ev: Event, user_id: str, steamid64: str) -> None:
    """删除该会话内该 steamid 的绑定。"""
    binds = await get_binds(ev, user_id)
    if not any(bind.steamid64 == steamid64 for bind in binds):
        raise ValueError("未找到该账户的绑定")

    await remove_bind(ev, user_id, steamid64)


async def send_bind_card(bot: Bot, ev: Event, user_id: str, *, force: bool = False) -> None:
    """渲染并发送绑定列表卡片；force 为真时重下资料图片。"""
    image = await render_bind_card_image(ev, user_id, force=force)
    await bot.send(MessageSegment.image(image))


def _bind_order(bind: SteamBind) -> int:
    """绑定顺序即主键顺序，与 steam查看 的卡片展示顺序一致。"""
    return bind.id


def _next_bind(binds: Sequence[SteamBind]) -> SteamBind:
    """当前主账号的下一位，末尾回绕首位；未设主账号时取第一位。"""
    for index, bind in enumerate(binds):
        if bind.is_main_id:
            return binds[(index + 1) % len(binds)]
    return binds[0]


def _resolve_bind(binds: Sequence[SteamBind], arg: str) -> SteamBind:
    """1-3 位纯数字按序号，其余按好友码 / steamid64。"""
    if arg.isdigit() and len(arg) <= 3:
        index = int(arg)
        if not 1 <= index <= len(binds):
            raise ValueError(f"没有第 {index} 个绑定账号")
        return binds[index - 1]

    steamid64 = auto2steamid64(arg)
    if steamid64 is None:
        raise ValueError("请传入好友码或账号序号")
    for bind in binds:
        if bind.steamid64 == steamid64:
            return bind
    raise ValueError("该账号不在当前绑定中")


async def switch_account(ev: Event, user_id: str, raw_arg: str) -> str:
    """切换当前会话主账号：按序号或好友码；无参数切到下一位。"""
    binds = sorted(await get_binds(ev, user_id), key=_bind_order)
    if not binds:
        raise ValueError("请先绑定 steam 账号")

    arg = raw_arg.strip()
    target = _resolve_bind(binds, arg) if arg else _next_bind(binds)

    bot_id, bot_self_id, group_id = session_ids(ev)
    switched = await SteamBind.set_main_id(user_id, bot_id, bot_self_id, group_id, target.steamid64)
    if not switched:
        raise ValueError("切换失败，请稍后重试")

    return f"已切换当前账号：{hide_id(steamid64_to_friend_code(target.steamid64))}"


async def refresh_bind_card(bot: Bot, ev: Event, user_id: str) -> None:
    """强制重下该会话绑定账号的资料图片并重发绑定卡片。"""
    if not await get_binds(ev, user_id):
        raise ValueError("请先绑定 steam 账号")
    await send_bind_card(bot, ev, user_id, force=True)
