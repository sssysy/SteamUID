import re
import asyncio
import httpx
from gsuid_core.logger import logger

from ..SteamConfig import SteamConfig, get_current_lang
from ..SteamConfig.interface import SteamAPI
from ..utils.exceptions import TIMEOUT_ERR_MSG, SteamTimeoutError


async def get_user_year_in_review_share_images(
    steamid64: str, year: int, language: str | None = None
) -> list[str]:
    """获取指定 steamid64 在指定年份的年度回顾分享图片 URL 列表。

    优先调用官方 Web API（ISaleFeatureService/GetUserYearInReviewShareImage/v1），
    该接口会返回包括 1080x1080、1080x1920、1200x628 等在内的预生成分享图片。
    若 API 请求失败或为空，回退到 Steam 商店页面解析 OpenGraph 元数据。
    若用户未公开或无数据，返回空列表。
    """
    if not language:
        language = get_current_lang()
    base_cdn = "https://shared.fastly.steamstatic.com/social_sharing/"
    image_urls: list[str] = []
    timeout_errors = 0

    # 1. 优先调用官方 Web API
    api_cfg = SteamConfig.get_config("APIBaseURL").data
    api_base_url = (
        api_cfg
        if isinstance(api_cfg, str) and api_cfg.strip()
        else "https://api.steampowered.com"
    ).rstrip("/")
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

    # 2. 回退：通过 Steam 商店年度回顾页面解析 OpenGraph 分享图
    store_cfg = SteamConfig.get_config("storeBaseURL").data
    store_base_url = (
        store_cfg
        if isinstance(store_cfg, str) and store_cfg.strip()
        else "https://store.steampowered.com"
    ).rstrip("/")
    store_url = f"{store_base_url}/replay/{steamid64}/{year}"

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(store_url, headers=headers)
            if resp.status_code == 200 and resp.text:
                og_matches = re.findall(
                    r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
                    resp.text,
                    re.IGNORECASE,
                )
                if not og_matches:
                    og_matches = re.findall(
                        r'<link\s+rel=["\']image_src["\']\s+href=["\']([^"\']+)["\']',
                        resp.text,
                        re.IGNORECASE,
                    )

                for img in og_matches:
                    img = img.strip()
                    # 排除未公开时的通用占位图
                    if (
                        "social_share_image_generic" in img
                        or "/public/images/yearinreview/" in img
                    ):
                        continue
                    if "social_sharing/replay" in img or "/social_sharing/" in img:
                        if img not in image_urls:
                            image_urls.append(img)
    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        logger.warning(
            f"[SteamUID] 商店页解析年度回顾分享图超时 steamid={steamid64} year={year}: {e}"
        )
        timeout_errors += 1
    except Exception as e:
        logger.warning(
            f"[SteamUID] 商店页解析年度回顾分享图异常 steamid={steamid64} year={year}: {e}"
        )

    if timeout_errors >= 2 and not image_urls:
        raise SteamTimeoutError(TIMEOUT_ERR_MSG)

    return image_urls
