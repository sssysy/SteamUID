import json
import time
from typing import Optional
import httpx

from gsuid_core.logger import logger
from ..database.models import SteamNextAccount
from ...SteamConfig import SteamConfig

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)

STEAM_DOMAINS = [
    "store.steampowered.com",
    "help.steampowered.com",
    "steamcommunity.com",
]


def get_proxy_url() -> Optional[str]:
    """从 SteamConfig 获取配置的代理 URL"""
    try:
        val = SteamConfig.get_config("HttpProxy").data
        if isinstance(val, str):
            proxy = val.strip()
            if proxy:
                if not proxy.startswith(("http://", "https://", "socks5://", "socks5h://")):
                    proxy = f"http://{proxy}"
                return proxy
    except Exception:
        pass
    return None


def get_proxy_dict() -> Optional[dict]:
    """从 SteamConfig 获取配置的代理字典（保留兼容性）"""
    proxy = get_proxy_url()
    if proxy:
        return {"http": proxy, "https": proxy}
    return None


async def get_account_session(steamid64: str) -> Optional[httpx.AsyncClient]:
    """
    根据 steamid64 从数据库构建带有已授权 Cookie 的 httpx.AsyncClient。
    """
    acc = await SteamNextAccount.get_account(steamid64)
    if not acc:
        logger.warning(f"[SteamNext] 未找到账号 {steamid64} 的授权凭据")
        return None

    proxy = get_proxy_url()
    client = httpx.AsyncClient(
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        proxy=proxy,
        timeout=15,
    )

    cookies: dict[str, str] = {}
    if acc.cookies_json:
        try:
            cookies = json.loads(acc.cookies_json)
        except Exception as e:
            logger.warning(f"[SteamNext] 解析账号 {steamid64} 的 Cookie 异常: {e}")

    # 如果存在独立的 session_id 或 access_token，确保合并入 cookies
    session_id = acc.session_id or cookies.get("sessionid")
    if session_id:
        cookies["sessionid"] = str(session_id)

    if acc.access_token:
        cookies["steamLoginSecure"] = f"{steamid64}||{acc.access_token}"

    for domain in STEAM_DOMAINS:
        for name, value in cookies.items():
            client.cookies.set(name, str(value), domain=domain)

    return client


async def refresh_account_tokens(steamid64: str) -> bool:
    """
    使用 refresh_token 刷新账号的 access_token，并同步写回数据库。
    """
    acc = await SteamNextAccount.get_account(steamid64)
    if not acc or not acc.refresh_token:
        logger.warning(f"[SteamNext] 账号 {steamid64} 不存在或无 refresh_token，无法刷新")
        return False

    url = "https://api.steampowered.com/IAuthenticationService/GenerateAccessTokenForApp/v1"
    data = {
        "refresh_token": acc.refresh_token,
        "steamid": steamid64,
    }

    proxy = get_proxy_url()
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=15) as client:
            resp = await client.post(url, data=data)
            if resp.status_code != 200:
                logger.error(f"[SteamNext] 刷新 token 请求失败: HTTP {resp.status_code}")
                return False

            res_json = resp.json()
            new_access_token = res_json.get("response", {}).get("access_token")
            if not new_access_token:
                logger.error(f"[SteamNext] 刷新 token 返回数据异常: {res_json}")
                return False

            # 更新已存的 cookies
            cookies = {}
            if acc.cookies_json:
                try:
                    cookies = json.loads(acc.cookies_json)
                except Exception:
                    pass
            cookies["steamLoginSecure"] = f"{steamid64}||{new_access_token}"

            await SteamNextAccount.upsert_account(
                steamid64=steamid64,
                access_token=new_access_token,
                cookies_json=json.dumps(cookies, ensure_ascii=False),
                updated_at=int(time.time()),
            )
            logger.info(f"[SteamNext] 账号 {steamid64} access_token 自动刷新成功")
            return True
    except Exception as e:
        logger.error(f"[SteamNext] 刷新 token 过程出现异常: {e}")
        return False


async def get_valid_session(steamid64: str, auto_refresh: bool = True) -> Optional[httpx.AsyncClient]:
    """
    获取有效且经过连通性校验的 Session，若失效且开启 auto_refresh 则自动刷新。
    """
    session = await get_account_session(steamid64)
    if not session:
        return None

    # 简易校验：测试请求一次登录个人资料页或商店接口
    try:
        test_url = "https://store.steampowered.com/account/"
        resp = await session.get(test_url, timeout=10, follow_redirects=False)
        # 如果重定向到 login 页面，说明凭据已过期
        if resp.status_code in (302, 301) and "login" in resp.headers.get("Location", ""):
            if auto_refresh:
                logger.info(f"[SteamNext] 账号 {steamid64} 网页 Session 已失效，尝试刷新...")
                await session.aclose()
                if await refresh_account_tokens(steamid64):
                    return await get_account_session(steamid64)
            else:
                await session.aclose()
            return None
    except Exception as e:
        logger.warning(f"[SteamNext] 检验 session 有效性异常: {e}")

    return session
