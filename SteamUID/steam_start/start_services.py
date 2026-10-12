"""启动自检：Steam API Key 缺失提示与 API 基址连通性 / 延迟探测。"""

import time

import httpx

from gsuid_core.logger import logger

from ..steam_config import SteamConfig
from ..utils.key_pool import has_api_key
from ..utils.api.public import get_server_info
from ..utils.helper.config import api_base

_TAG = "[SteamUID]"


async def api_key_startup_check() -> None:
    """Key 缺失只提示不中断启动，依赖 Key 的功能在调用时各自报错。"""
    if has_api_key(SteamConfig.get_config("SteamAPIKey").data):
        return

    logger.error(f"{_TAG} 未检测到 Steam API Key，用户状态轮询等依赖 Key 的功能不可用，请在控制台配置")


async def api_connectivity_startup_check() -> None:
    """探测配置的 API 基址并打出延迟，失败只记录日志、不中断启动。"""
    base = api_base()
    started = time.perf_counter()
    try:
        await get_server_info(base_url=base)
    except (httpx.HTTPError, ValueError) as error:
        # 反代配错时可能返回非 JSON 页面，这里只报告失败原因，不中断启动
        reason = (
            f"HTTP {error.response.status_code}" if isinstance(error, httpx.HTTPStatusError) else type(error).__name__
        )
        logger.error(f"{_TAG} Steam API 连通性检测失败: {reason} ({base})")
        return

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(f"{_TAG} Steam API 连通性检测通过，延迟 {elapsed_ms:.0f}ms")
