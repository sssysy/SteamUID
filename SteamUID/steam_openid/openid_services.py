"""Steam OpenID 绑定 / 解绑 / 查看 的实现与网页回调路由。"""

import time
import asyncio
import secrets
from dataclasses import dataclass
from collections.abc import Sequence

from fastapi import Request
from starlette.responses import Response, RedirectResponse, PlainTextResponse

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.web_app import app

from ..steam_config import get_base_url
from ..utils.api.openid import build_login_url, verify_callback, extract_steamid64
from ..utils.downloader import download
from ..utils.helper.command import sender_text
from ..utils.helper.profile import load_profile_assets
from ..utils.helper.steamid import steamid64_to_friend_code
from ..utils.database.model_auth import SteamAuth
from ..utils.database.model_bind import SteamBind
from ..utils.render.html.bind_list import BindCardItem, render_bind_list
from ..utils.render.html.static_assets import get_img_cache_url, get_default_avatar_url

_TAG = "[Steam·账户绑定]"
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

    base = get_base_url()
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
    base = get_base_url()
    if not base:
        raise ValueError("未配置 GsCore 公网地址，无法发起 Steam 网页登录")

    state = secrets.token_urlsafe(16)
    session = _LoginSession(state=state, created_at=time.monotonic())
    _SESSIONS[state] = session

    await bot.send(f"请在 {int(_OPENID_TTL)} 秒内打开链接完成 Steam 登录：\n{base}/steam/openid?state={state}")

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


def _session_ids(ev: Event) -> tuple[str, str, str]:
    return ev.bot_id, ev.bot_self_id, ev.group_id or ""


async def bind_account(ev: Event, user_id: str, steamid64: str) -> None:
    """校验并写入绑定，新绑定设为当前账户。"""
    profile = await load_profile_assets(steamid64)
    bot_id, bot_self_id, group_id = _session_ids(ev)

    binds = await SteamBind.get_binds_by_session(user_id, bot_id, bot_self_id, group_id)
    if any(bind.steamid64 == steamid64 for bind in binds):
        raise ValueError(f"该账户已绑定：[{profile.name}]")

    await SteamBind.upsert_bind(
        user_id=user_id,
        bot_id=bot_id,
        bot_self_id=bot_self_id,
        group_id=group_id,
        steamid64=steamid64,
        WS_BOT_ID=ev.WS_BOT_ID,
        is_main_id=True,
    )


async def unbind_account(ev: Event, user_id: str, steamid64: str) -> None:
    """删除当前会话内该 steamid 的绑定。"""
    bot_id, bot_self_id, group_id = _session_ids(ev)
    binds = await SteamBind.get_binds_by_session(user_id, bot_id, bot_self_id, group_id)
    if not any(bind.steamid64 == steamid64 for bind in binds):
        raise ValueError("未找到该账户的绑定")

    await SteamBind.delete_bind(user_id, bot_id, bot_self_id, group_id, steamid64)


async def _is_logged_in(steamid64: str) -> bool:
    account = await SteamAuth.get_account(steamid64)
    if account is None:
        return False
    return bool(account.access_token or account.refresh_token)


async def _load_card_item(bind: SteamBind, group_id: str) -> BindCardItem:
    """组装单个药丸数据；资料抓取失败时回落默认昵称与头像，不影响其它账户。"""
    profile, is_login = await asyncio.gather(
        load_profile_assets(bind.steamid64),
        _is_logged_in(bind.steamid64),
        return_exceptions=True,
    )

    if isinstance(profile, BaseException):
        logger.warning(f"{_TAG} 卡片资料获取失败 {bind.steamid64}: {profile!r}")
        name = bind.steamid64
        friend_code = steamid64_to_friend_code(bind.steamid64)
        avatar_url = get_default_avatar_url()
        frame_url = ""
        background_url = ""
    else:
        name = profile.name
        friend_code = profile.friend_code
        avatar_url = get_img_cache_url(profile.avatar_name) or get_default_avatar_url()
        frame_url = get_img_cache_url(profile.frame_name)
        background_url = get_img_cache_url(profile.background_name)

    if isinstance(is_login, BaseException):
        logger.warning(f"{_TAG} 登录状态查询失败 {bind.steamid64}: {is_login!r}")
        logged_in = False
    else:
        logged_in = is_login

    return BindCardItem(
        name=name,
        friend_code=friend_code,
        avatar_url=avatar_url,
        frame_url=frame_url,
        background_url=background_url,
        is_main=bool(bind.is_main_id and bind.group_id == group_id),
        is_login=logged_in,
    )


async def _build_card_items(binds: Sequence[SteamBind], group_id: str) -> list[BindCardItem]:
    return list(await asyncio.gather(*(_load_card_item(bind, group_id) for bind in binds)))


async def _resolve_qq_avatar(ev: Event) -> str:
    """群聊头像经 downloader 落 img_cache 后取直链，缺失回落默认头像。"""
    url = sender_text(ev, "avatar")
    if url.startswith(("http://", "https://")):
        path = await download(url, kind="image")
        if path is not None:
            return get_img_cache_url(path.name)
    return get_default_avatar_url()


async def send_bind_card(bot: Bot, ev: Event, user_id: str) -> None:
    """渲染并发送绑定列表卡片。"""
    bot_id, bot_self_id, group_id = _session_ids(ev)
    binds = await SteamBind.get_binds_by_session(user_id, bot_id, bot_self_id, group_id)

    items = await _build_card_items(binds, group_id)
    user_name = sender_text(ev, "nickname") or user_id
    qq_avatar_url = await _resolve_qq_avatar(ev)
    image = await render_bind_list(items, user_name=user_name, qq_avatar_url=qq_avatar_url)
    await bot.send(MessageSegment.image(image))
