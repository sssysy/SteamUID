"""命令层通用封装：参数分层解析与命令错误边界。"""

from functools import wraps
from collections.abc import Callable, Awaitable

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .steamid import auto2steamid64

_TAG = "[Steam·账户绑定]"


def sender_text(ev: Event, key: str) -> str:
    """读取 ev.sender 中的字符串字段；缺失或非字符串回落空串。"""
    if key not in ev.sender:
        return ""
    value = ev.sender[key]
    if isinstance(value, str):
        return value
    return ""


def resolve_target(ev: Event, *, allow_at: bool) -> tuple[str, str | None]:
    """分层解析目标：@ 层（受开关约束）→ steamid / 好友码层。"""
    user_id = ev.user_id
    if ev.at:
        if not allow_at:
            raise ValueError("管理员未开放 @ 他人功能")
        user_id = ev.at
    return user_id, auto2steamid64(ev.text)


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
        except Exception as e:
            logger.exception(f"{_TAG} 命令执行失败: {e!r}")
            await bot.send("操作失败，请稍后重试")

    return wrapper
