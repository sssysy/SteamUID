"""命令层通用封装：参数分层解析与命令错误边界。"""

from functools import wraps
from collections.abc import Callable, Awaitable

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .steamid import auto2steamid64, parse_profile_page
from ..key_pool import has_api_key
from .steam_api import fetch_vanity_steamid64
from ...steam_config import SteamConfig

_TAG = "[Steam·账户绑定]"
_NET_TAG = "[Steam·网络请求]"
_KEY_TAG = "[Steam·密钥池]"

# Key 被拒时接口用 401 / 403，正文固定带这段提示，据此区分站点自身的 403
_KEY_DENIED_CODES = frozenset({httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN})
_KEY_DENIED_MARK = "verify your <pre>key=</pre> parameter"
_NO_KEY_HINT = "无可用API Key，请检查当前所有 Key 可用状态"


def sender_text(ev: Event, key: str) -> str:
    """读取 ev.sender 中的字符串字段；缺失或非字符串回落空串。"""
    if key not in ev.sender:
        return ""
    value = ev.sender[key]
    if isinstance(value, str):
        return value
    return ""


async def resolve_target(ev: Event, *, allow_at: bool) -> tuple[str, str | None]:
    """分层解析目标：@ 层（受开关约束）→ 个人资料页 / steamid / 好友码层。"""
    user_id = ev.user_id
    if ev.at:
        if not allow_at:
            raise ValueError("管理员未开放 @ 他人功能")
        user_id = ev.at
    return user_id, await resolve_steamid64(ev.text)


async def resolve_steamid64(raw: str) -> str | None:
    """把个人资料页 / steamid / 好友码统一成 steamid64；无法识别返回 None。"""
    direct = auto2steamid64(raw)
    if direct is not None:
        return direct

    page = parse_profile_page(raw)
    if page is None:
        return None
    if page.kind == "steamid64":
        return page.value

    keys = SteamConfig.get_config("SteamAPIKey").data
    if not has_api_key(keys):
        raise ValueError("未配置 Steam API Key，无法解析个人资料页")
    steamid64 = await fetch_vanity_steamid64(
        page.value,
        keys=keys,
        cooldown=SteamConfig.get_config("KeyPoolCooldown").data,
    )
    if steamid64 is None:
        raise ValueError("未找到该个人资料页中的账号")
    return steamid64


def resolve_viewer(ev: Event, *, allow_at: bool) -> str:
    """解析发起人：@ 他人（受开关约束）优先，否则取消息发送者。

    与 resolve_target 的区别是不解析消息正文，供正文是游戏名等非账号参数的命令使用。
    """
    if ev.at:
        if not allow_at:
            raise ValueError("管理员未开放 @ 他人功能")
        return ev.at
    return ev.user_id


def _is_key_denied(error: httpx.HTTPStatusError) -> bool:
    """是否 Steam 拒绝 API Key；商店等站点自身的 403 不算。"""
    if error.response.status_code not in _KEY_DENIED_CODES:
        return False
    return _KEY_DENIED_MARK in error.response.text


async def _reply_failure(bot: Bot, error: Exception) -> None:
    """未知错误的统一回执：详细信息只进日志。"""
    logger.exception(f"{_TAG} 命令执行失败: {error!r}")
    await bot.send("操作失败，请稍后重试")


def command_guard(
    func: Callable[[Bot, Event], Awaitable[None]],
) -> Callable[[Bot, Event], Awaitable[None]]:
    """命令错误边界：校验类错误回执原文，未知错误写日志并提示用户。"""

    @wraps(func)
    async def wrapper(bot: Bot, ev: Event) -> None:
        try:
            await func(bot, ev)
        except ValueError as e:
            await bot.send(str(e))
        except httpx.TimeoutException as e:
            logger.warning(f"{_NET_TAG} 连接 Steam 超时: {type(e).__name__}")
            await bot.send("连接 Steam 超时，请稍后重试")
        except httpx.HTTPStatusError as e:
            if _is_key_denied(e):
                logger.warning(f"{_KEY_TAG} API Key 被拒绝，HTTP {e.response.status_code}")
                await bot.send(_NO_KEY_HINT)
            else:
                await _reply_failure(bot, e)
        except Exception as e:
            await _reply_failure(bot, e)

    return wrapper
