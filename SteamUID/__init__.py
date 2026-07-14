from gsuid_core.sv import Plugins
from gsuid_core.server import on_core_start
from gsuid_core.logger import logger
from .SteamConfig.interface import SteamAPI
import httpx

Plugins(
    name="SteamUID",
    force_prefix=["steam"],
    allow_empty_prefix=False,
)

@on_core_start
async def check():
    # 提醒配置steam api key
    from .SteamConfig import SteamConfig
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        logger.warning("[SteamUID] 未检测到 steam web api key，请尽快配置，否则本插件大部分功能将无法使用！")
    
    # 判断是否能连上steam api
    api_url = SteamConfig.get_config("APIBaseURL").data
    test_url = f"{api_url}{SteamAPI.api_GetServerInfo}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(test_url)
            if resp.status_code != 200:
                logger.error(f"[SteamUID] 连接 steam api 返回异常: {resp.status_code}，当前baseurl: {api_url}")
                return
            else:
                logger.success(f"[SteamUID] 当前baseurl: {api_url} 连通性测试成功！")
    except httpx.TimeoutException as e:
        logger.error(f"[SteamUID] 连接 steam api 超时，当前baseurl: {api_url}")
        return
    except Exception as e:
        logger.error(f"[SteamUID] 连接 steam api 失败，当前baseurl: {api_url}, 错误信息: {e}")
        return
