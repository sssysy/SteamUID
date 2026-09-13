from typing import Any

TIMEOUT_ERR_MSG = "网络请求超时，请检查后台代理设置或重试。"


class SteamError(Exception):
    """str(e) 即用户可见错误消息"""


class SteamValidationError(SteamError):
    """业务校验失败（绑定冲突、未绑定、参数无效等）"""


class SteamAPIError(SteamError):
    """Steam API 请求失败"""


class SteamRenderError(SteamError):
    """图片渲染失败"""


class SteamTimeoutError(SteamError):
    """网络请求或渲染超时"""

    def __init__(self, message: str = TIMEOUT_ERR_MSG):
        super().__init__(message)


class SteamConfigError(SteamError):
    """配置缺失或无效"""


class SteamAlreadyBoundBySelf(SteamValidationError):
    """该 steamid 已由当前用户在同一群绑定（重复登录 / 重复绑定，凭据可静默更新）"""


class SteamBoundByOthers(SteamValidationError):
    """该 steamid 已被其他用户绑定"""


def unwrap(result: Any, default: Any, *, expect: type | tuple[type, ...] = ()) -> Any:
    """解包 ``asyncio.gather(..., return_exceptions=True)`` 的结果"""
    if isinstance(result, BaseException):
        return default
    if expect and not isinstance(result, expect):
        return default
    return result

