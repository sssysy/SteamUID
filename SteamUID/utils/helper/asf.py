"""ASF 配置派生：启用开关、根地址与认证密码。"""

from dataclasses import dataclass

from ..asf.client import AsfEndpoint
from ...steam_config import SteamConfig
from ..asf.endpoints import ASF_API_PREFIX


@dataclass(frozen=True)
class AsfSettings:
    enabled: bool
    base_url: str
    password: str


def _api_base(raw: str) -> str:
    """把用户填写的 ASF 根地址规整为 API 根，重复的 /Api 只保留一次。"""
    base = raw.strip().rstrip("/")
    if not base:
        return ""
    if base.endswith(ASF_API_PREFIX):
        return base
    return f"{base}{ASF_API_PREFIX}"


def asf_settings() -> AsfSettings:
    """读取当前 ASF 配置；调用方必须先检查 enabled。"""
    enabled = SteamConfig.get_config("ASFEnabled").data
    raw_base = SteamConfig.get_config("ASFServerURL").data
    password = SteamConfig.get_config("ASFPassword").data.strip()
    return AsfSettings(
        enabled=enabled,
        base_url=_api_base(raw_base),
        password=password,
    )


def asf_endpoint() -> AsfEndpoint:
    """构造传输层需要的端点；未启用或地址为空时报用户可见错误。"""
    settings = asf_settings()
    if not settings.enabled:
        raise ValueError("ASF 相关功能未启用")
    if not settings.base_url:
        raise ValueError("请先配置 ASF 服务器地址")
    return AsfEndpoint(base_url=settings.base_url, password=settings.password)
