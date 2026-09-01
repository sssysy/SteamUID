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

