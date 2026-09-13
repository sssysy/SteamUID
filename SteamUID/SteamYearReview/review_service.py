import asyncio
import httpx
from gsuid_core.logger import logger

from ..SteamConfig import SteamConfig, get_current_lang
from ..SteamConfig.interface import SteamAPI
from ..utils.exceptions import TIMEOUT_ERR_MSG, SteamTimeoutError


async def get_user_year_in_review_share_images(
    steamid64: str, year: int, language: str | None = None
) -> list[str]:
    """获取指定 steamid64 在指定年份的年度回顾分享图片 URL 列表。"""
    if not language:
        language = get_current_lang()
    base_cdn = "https://shared.fastly.steamstatic.com/social_sharing/"
    image_urls: list[str] = []
    timeout_errors = 0

    # 1. 优先调用官方 Web API
    api_base_url = SteamConfig.get_config("APIBaseURL").data.strip().rstrip("/")
    api_url = f"{api_base_url}{SteamAPI.api_GetUserYearInReviewShareImage}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://store.steampowered.com",
        "Referer": f"https://store.steampowered.com/replay/{steamid64}/{year}",
    }

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                api_url,
                params={"steamid": steamid64, "year": year, "language": language},
                headers=headers,
            )
            if resp.status_code == 200 and resp.text:
                data = resp.json()
                images = data.get("response", {}).get("images", [])
                for img in images:
                    url_path = img.get("url_path")
                    if url_path:
                        full_url = f"{base_cdn}{url_path.lstrip('/')}"
                        if full_url not in image_urls:
                            image_urls.append(full_url)
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.warning(
            f"[SteamUID] WebAPI 获取年度回顾分享图超时 steamid={steamid64} year={year}: {e}"
        )
        timeout_errors += 1
    except Exception as e:
        logger.warning(
            f"[SteamUID] WebAPI 获取年度回顾分享图异常 steamid={steamid64} year={year}: {e}"
        )

    if image_urls:
        return image_urls

    if timeout_errors:
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)

    return image_urls
