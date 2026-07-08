class SteamError(Exception):
    """str(e) 即用户可见错误消息"""


class SteamValidationError(SteamError):
    """业务校验失败（绑定冲突、未绑定、参数无效等）"""


class SteamAPIError(SteamError):
    """Steam API 请求失败"""


class SteamRenderError(SteamError):
    """图片渲染失败"""


class SteamConfigError(SteamError):
    """配置缺失或无效"""
