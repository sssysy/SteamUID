"""Steam 年度回顾：取官方分享图直链，落 img_cache 后返回本地图片。"""

from pathlib import Path
from datetime import datetime

from gsuid_core.sv import get_plugin_available_prefix

from ..utils.api.public import get_year_in_review_share_images
from ..utils.downloader import download
from ..utils.api.endpoints import SHARED_CDN_BASE_DEFAULT

# 分享图由服务端按语言渲染图文，这里固定中文
_LANGUAGE = "schinese"
# 与商店前端 BASE_URL_SHARED_CDN + social_sharing/ 的拼接方式一致
_SHARE_CDN_PREFIX = f"{SHARED_CDN_BASE_DEFAULT}/social_sharing/"
# Steam 年度回顾自 2022 年起提供
_MIN_YEAR = 2022


def _usage() -> str:
    """用户可见的用法提示，前缀取插件实际配置值。"""
    prefix = get_plugin_available_prefix("SteamUID")
    return f"{prefix}年度回顾 [年份]"


def parse_year(text: str) -> int:
    """解析年份实参：空参取上一年，非四位数字或实参多于一个即报用法错误。"""
    tokens = text.split()
    if not tokens:
        return datetime.now().year - 1

    first = tokens[0]
    if len(tokens) > 1 or len(first) != 4 or not first.isdigit():
        raise ValueError(f"参数错误，正确用法：{_usage()}")

    year = int(first)
    if year < _MIN_YEAR:
        raise ValueError(f"参数错误，正确用法：{_usage()}")
    return year


async def fetch_year_review_images(steamid64: str, year: int) -> list[Path]:
    """取该账号该年的官方分享图并落 img_cache；未公开或无数据返回空列表。"""
    payload = await get_year_in_review_share_images(steamid64, year, language=_LANGUAGE)
    images = payload["images"] if "images" in payload else []
    urls = [f"{_SHARE_CDN_PREFIX}{image['url_path']}" for image in images if "url_path" in image and image["url_path"]]
    if not urls:
        return []

    paths = await download(urls, kind="image")
    return [path for path in paths if path is not None]
