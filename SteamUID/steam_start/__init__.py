"""启动自检注册：API Key 配置检测与 API 连通性探测。"""

from gsuid_core.server import on_core_start

from .start_services import (
    api_key_startup_check,
    api_connectivity_startup_check,
)

on_core_start(api_key_startup_check)
on_core_start(api_connectivity_startup_check)
