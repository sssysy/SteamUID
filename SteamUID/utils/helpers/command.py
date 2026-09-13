"""命令层统一异常兜底装饰器"""

from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable

from gsuid_core.logger import logger

from ..exceptions import SteamError

UNKNOWN_ERR_MSG = "发生未知错误，详情请查看后台。"


def steam_command(name: str, fallback: str = UNKNOWN_ERR_MSG) -> Callable:
    """统一命令级兜底：业务异常直接回显，未预期异常记堆栈后回兜底文案。"""

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(bot: Any, ev: Any) -> None:
            try:
                await fn(bot, ev)
            except SteamError as e:
                await bot.send(str(e))
            except Exception as e:
                logger.exception(f"[{name}] 未知错误: {e!r}")
                await bot.send(fallback)

        return wrapper

    return deco
